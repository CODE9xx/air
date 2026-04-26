"""
AmoCrmConnector — реальный коннектор к amoCRM.

В MVP:

* `oauth_authorize_url`  — готов (используется в OAuth-start).
* `exchange_code`        — REAL (Phase 2A step 2): POST на /oauth2/access_token.
* `refresh`              — REAL (Phase 2A step 3).
* `fetch_account`        — REAL (Phase 2A step 2): GET /api/v4/account.
* `fetch_pipelines`      — REAL (Phase 2A step 4): GET /api/v4/leads/pipelines.
* `fetch_stages`         — REAL (Phase 2A step 4): читает /leads/pipelines
  и эмитит статусы (amoCRM кладёт статусы вложенными в pipeline).
* `fetch_users`          — REAL (Phase 2A step 4): GET /api/v4/users.
* `fetch_deals`          — REAL (Phase 2A step 4): GET /api/v4/leads
  с пагинацией и `since` через `filter[updated_at][from]`.
* `fetch_contacts`       — REAL (Phase 2A step 4): GET /api/v4/contacts.
* `fetch_companies`      — REAL (Phase 2B step 1): GET /api/v4/companies.
* остальные `fetch_*`    — NotImplementedError, Phase 2B/2C (calls, chats,
  tasks, notes) — см. ``docs/api/CONTRACT.md §CRM``.

Endpoint-ы amoCRM:

* OAuth authorize — ``https://www.amocrm.com/oauth`` (общий, не зависит от
  субдомена).
* OAuth token exchange + refresh — ``https://{subdomain}.amocrm.ru/oauth2/access_token``.
  Субдомен в amoCRM === «account slug» — он приходит в query callback'а
  как параметр ``referer``, либо вычисляется из ``account.subdomain`` после
  первого ``fetch_account``. Для exchange_code мы вынуждены знать его
  заранее → BE кладёт его в state Redis до редиректа (см. oauth_router.py).
* API v4 — ``https://{subdomain}.amocrm.ru/api/v4/...``.

Security:

* access_token / refresh_token НИКОГДА не логируются. ``TokenPair.raw``
  нужен только для отладочной трассировки внутри worker'а — лог-маска
  (``worker/lib/log_mask.py``) глушит ``access_token`` / ``refresh_token``.
* Ошибки сети/HTTP оборачиваются в доменные исключения
  (``TokenExpired`` / ``InvalidGrant`` / ``RateLimited`` / ``ProviderError``).
  Исключения не содержат `client_secret`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import time
from typing import Any, Iterable, Optional
from urllib.parse import urlencode

import httpx

from .base import (
    CRMConnector,
    RawCall,
    RawCompany,
    RawContact,
    RawCustomField,
    RawDeal,
    RawEvent,
    RawMessage,
    RawNote,
    RawPipeline,
    RawProduct,
    RawStage,
    RawTask,
    RawUser,
    TokenPair,
)
from .enums import Provider
from .exceptions import InvalidGrant, ProviderError, RateLimited, TokenExpired

_AMO_AUTHORIZE_URL = "https://www.amocrm.com/oauth"
_V1_NOT_IMPLEMENTED_MSG = (
    "AmoCrmConnector.{method}: реальная интеграция с amoCRM — V1. "
    "В MVP используется MOCK_CRM_MODE=true → MockCRMConnector."
)

# Буфер на часовые рассинхроны между nginx/приложением и amoCRM:
# если до expires_at осталось меньше чем _EXPIRY_SAFETY_SECONDS,
# worker запустит refresh сразу, не дожидаясь фактической экспирации.
_EXPIRY_SAFETY_SECONDS = 60
_PAGINATED_GET_MAX_ATTEMPTS = 4
_PAGINATED_GET_RETRY_BASE_SECONDS = 1.0
_DEFAULT_AMOCRM_API_MAX_RPS = 5.0


class AmoCrmConnector(CRMConnector):
    """
    Реальный клиент amoCRM.

    Конструктор:
        client_id, client_secret: OAuth-приложение amoCRM (AMOCRM_CLIENT_ID /
            AMOCRM_CLIENT_SECRET). Читается из env на стороне API/worker
            (см. ``apps/api/app/core/settings.py``).
        subdomain: account slug (``https://{subdomain}.amocrm.ru``). Нужен для
            token endpoint'а и всех API v4 вызовов. Может быть ``None`` на
            этапе OAuth-start (до знания аккаунта) — но обязателен на
            ``exchange_code`` и далее.
        http_timeout: таймаут httpx-клиента (сек). 30s достаточно для v4 API.
        max_requests_per_second: локальный лимит на этот connector instance.
            По умолчанию берётся AMOCRM_API_MAX_RPS или 5 rps, что ниже
            официального лимита 7 rps на одну интеграцию.
    """

    provider: Provider = Provider.AMOCRM

    def __init__(
        self,
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
        http_timeout: float = 30.0,
        subdomain: str | None = None,
        max_requests_per_second: float | None = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._http_timeout = http_timeout
        self._subdomain = subdomain
        self._max_requests_per_second = self._resolve_max_requests_per_second(
            max_requests_per_second
        )
        self._last_request_monotonic = 0.0

    # ----- helpers ------------------------------------------------------------

    @staticmethod
    def _resolve_max_requests_per_second(value: float | None) -> float:
        if value is not None:
            return max(0.1, float(value))
        raw = os.getenv("AMOCRM_API_MAX_RPS")
        if raw:
            try:
                return max(0.1, float(raw))
            except ValueError:
                return _DEFAULT_AMOCRM_API_MAX_RPS
        return _DEFAULT_AMOCRM_API_MAX_RPS

    def _throttle_api_request(self) -> None:
        """Keep one integration below amoCRM's default 7 rps API limit."""
        if self._max_requests_per_second <= 0:
            return
        min_interval = 1.0 / self._max_requests_per_second
        now = time.monotonic()
        wait_for = min_interval - (now - self._last_request_monotonic)
        if wait_for > 0:
            time.sleep(wait_for)
        self._last_request_monotonic = time.monotonic()

    @staticmethod
    def _retry_after_seconds(response: httpx.Response, body: Any, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after is None and isinstance(body, dict):
            retry_after = body.get("retry_after")
        if retry_after is not None:
            try:
                return min(60.0, max(1.0, float(retry_after)))
            except (TypeError, ValueError):
                pass
        return min(30.0, _PAGINATED_GET_RETRY_BASE_SECONDS * (2 ** max(0, attempt - 1)))


    def _token_url(self) -> str:
        """URL для exchange_code / refresh."""
        if not self._subdomain:
            raise ProviderError(
                "AmoCrmConnector: subdomain не задан — не знаю, куда слать "
                "POST /oauth2/access_token. Передай subdomain в конструктор.",
                provider=self.provider.value,
            )
        return f"https://{self._subdomain}.amocrm.ru/oauth2/access_token"

    def _api_url(self, path: str) -> str:
        """URL для API v4."""
        if not self._subdomain:
            raise ProviderError(
                "AmoCrmConnector: subdomain не задан — API v4 вызвать невозможно.",
                provider=self.provider.value,
            )
        return f"https://{self._subdomain}.amocrm.ru/api/v4/{path.lstrip('/')}"

    def _account_url(self, path: str) -> str:
        """URL for account web/AJAX endpoints. Experimental, backend-only."""
        if not self._subdomain:
            raise ProviderError(
                "AmoCrmConnector: subdomain не задан — account endpoint вызвать невозможно.",
                provider=self.provider.value,
            )
        return f"https://{self._subdomain}.amocrm.ru/{path.lstrip('/')}"

    def _token_pair_from_response(
        self, data: dict[str, Any]
    ) -> TokenPair:
        """
        Нормализует JSON `POST /oauth2/access_token` → `TokenPair`.

        amoCRM возвращает:
            {
              "token_type": "Bearer",
              "expires_in": 86400,       # сек
              "access_token": "...",
              "refresh_token": "..."
            }
        """
        access = data.get("access_token")
        refresh = data.get("refresh_token")
        expires_in = data.get("expires_in")
        if not access or not refresh or not isinstance(expires_in, (int, float)):
            raise ProviderError(
                "amoCRM вернул неполный OAuth-ответ",
                provider=self.provider.value,
                payload={"keys": sorted(data.keys())},
            )
        expires_at = datetime.now(tz=timezone.utc) + timedelta(
            seconds=int(expires_in) - _EXPIRY_SAFETY_SECONDS
        )
        return TokenPair(
            access_token=access,
            refresh_token=refresh,
            expires_at=expires_at,
            raw=data,
        )

    def _post_token(self, payload: dict[str, Any]) -> TokenPair:
        """
        Общий helper для exchange_code и refresh.

        Обрабатывает сетевые ошибки через httpx.RequestError и
        маппит HTTP-коды через `_raise_for_status`.
        """
        url = self._token_url()
        try:
            with httpx.Client(timeout=self._http_timeout) as client:
                self._throttle_api_request()
                response = client.post(
                    url,
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "User-Agent": "code9-analytics/1.0",
                    },
                )
        except httpx.RequestError as exc:
            # Сетевые проблемы (таймаут, DNS, TLS) — НЕ помечаем как InvalidGrant.
            # Это retryable — worker увидит ProviderError и попробует снова.
            raise ProviderError(
                f"amoCRM token endpoint unreachable: {type(exc).__name__}",
                provider=self.provider.value,
            ) from None

        # Попытаемся распарсить JSON — amoCRM возвращает JSON и на ошибках.
        try:
            body: Any = response.json()
        except ValueError:
            body = {"text": response.text[:500]}

        # Маппинг HTTP-кодов → наши исключения.
        self._raise_for_status(response.status_code, body)

        if response.status_code // 100 != 2:
            # 4xx, который _raise_for_status не поймал (например, 403).
            raise ProviderError(
                f"amoCRM token endpoint returned {response.status_code}",
                provider=self.provider.value,
                status_code=response.status_code,
                payload=body,
            )

        if not isinstance(body, dict):
            raise ProviderError(
                "amoCRM token endpoint вернул не-JSON объект",
                provider=self.provider.value,
                payload={"type": type(body).__name__},
            )

        return self._token_pair_from_response(body)

    # ----- API v4 helpers -----------------------------------------------------

    @staticmethod
    def _to_epoch(dt: datetime) -> int:
        """datetime → unix seconds (UTC). amoCRM принимает int-секунды."""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())

    @staticmethod
    def _from_epoch(ts: Any) -> Optional[datetime]:
        """unix seconds → timezone-aware UTC datetime. None/битое → None."""
        if ts is None or ts == 0:
            return None
        try:
            return datetime.fromtimestamp(int(ts), tz=timezone.utc)
        except (ValueError, TypeError, OverflowError):
            return None

    @staticmethod
    def _extract_phone_email(
        custom_fields_values: Any,
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Достаёт первый телефон и первый email из ``custom_fields_values``.

        amoCRM формат:
            [{"field_code": "PHONE", "values": [{"value": "+7..."}]}, ...]

        Опираемся на ``field_code`` (стабильный ключ), а не ``field_id``
        (уникален per-account). У одного контакта может быть несколько
        телефонов — берём первый.
        """
        phone: Optional[str] = None
        email: Optional[str] = None
        if not isinstance(custom_fields_values, list):
            return phone, email
        for cfv in custom_fields_values:
            if not isinstance(cfv, dict):
                continue
            code = cfv.get("field_code")
            values = cfv.get("values")
            if not isinstance(values, list) or not values:
                continue
            first = values[0]
            if not isinstance(first, dict):
                continue
            val = first.get("value")
            if not isinstance(val, str) or not val:
                continue
            if code == "PHONE" and phone is None:
                phone = val
            elif code == "EMAIL" and email is None:
                email = val
        return phone, email

    @staticmethod
    def _first_custom_field_value(
        custom_fields_values: Any,
        *,
        field_codes: set[str] | None = None,
        field_name_contains: tuple[str, ...] = (),
    ) -> Optional[str]:
        """Return first string custom-field value matching stable code or name hint."""
        if not isinstance(custom_fields_values, list):
            return None
        normalized_codes = {code.upper() for code in (field_codes or set())}
        normalized_names = tuple(part.lower() for part in field_name_contains)
        for cfv in custom_fields_values:
            if not isinstance(cfv, dict):
                continue
            code = str(cfv.get("field_code") or "").upper()
            name = str(cfv.get("field_name") or "").lower()
            if normalized_codes and code in normalized_codes:
                matched = True
            elif normalized_names and any(part in name for part in normalized_names):
                matched = True
            else:
                matched = False
            if not matched:
                continue
            values = cfv.get("values")
            if not isinstance(values, list) or not values:
                continue
            first = values[0]
            if not isinstance(first, dict):
                continue
            value = first.get("value")
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, (int, float)):
                return str(value)
        return None

    def _paginated_get(
        self,
        path: str,
        access_token: str,
        *,
        items_key: str,
        params: dict[str, Any] | None = None,
        page_limit: int = 250,
    ) -> Iterable[dict[str, Any]]:
        """
        Общая пагинация amoCRM API v4.

        Формат ответа::

            {
              "_page": 1,
              "_links": {"self": {...}, "next": {"href": "<full URL>"}},
              "_embedded": {"<items_key>": [...]}
            }

        Правила:

        * Идём по ``_links.next.href`` пока он есть.
        * ``page_limit`` вклеивается как ``limit`` в параметры первой
          страницы. amoCRM допускает ≤ 250 — больше возвращает 400.
        * 204 No Content → пустой список, stop iteration (amoCRM возвращает
          204 на фильтры, которые ничего не матчат).
        * Сетевые ошибки → ``ProviderError`` (retryable).
        * 401/429/4xx+hint=invalid_grant → доменные исключения через
          ``_raise_for_status`` (не логируем здесь — логи на стороне worker).

        ``next.href`` уже содержит полный query string, поэтому на последующих
        страницах мы не передаём ``params`` отдельно.
        """
        url: Optional[str] = self._api_url(path)
        first_params: dict[str, Any] = dict(params or {})
        first_params.setdefault("limit", page_limit)
        current_params: Optional[dict[str, Any]] = first_params

        with httpx.Client(timeout=self._http_timeout) as client:
            while url:
                response = None
                last_request_error: httpx.RequestError | None = None
                for attempt in range(1, _PAGINATED_GET_MAX_ATTEMPTS + 1):
                    try:
                        self._throttle_api_request()
                        response = client.get(
                            url,
                            params=current_params,
                            headers={
                                "Authorization": f"Bearer {access_token}",
                                "Accept": "application/json",
                                "User-Agent": "code9-analytics/1.0",
                            },
                        )
                        break
                    except httpx.RequestError as exc:
                        last_request_error = exc
                        if attempt >= _PAGINATED_GET_MAX_ATTEMPTS:
                            raise ProviderError(
                                f"amoCRM {path} unreachable after "
                                f"{_PAGINATED_GET_MAX_ATTEMPTS} attempts: "
                                f"{type(exc).__name__}",
                                provider=self.provider.value,
                            ) from None
                        time.sleep(_PAGINATED_GET_RETRY_BASE_SECONDS * (2 ** (attempt - 1)))

                if response is None:
                    exc_name = type(last_request_error).__name__ if last_request_error else "unknown"
                    raise ProviderError(
                        f"amoCRM {path} unreachable: {exc_name}",
                        provider=self.provider.value,
                    )

                if response.status_code == 204:
                    return

                try:
                    body: Any = response.json()
                except ValueError:
                    body = {"text": response.text[:500]}

                if response.status_code == 429 or response.status_code >= 500:
                    retry_attempts = getattr(self, "_paginated_retry_attempts", 0) + 1
                    setattr(self, "_paginated_retry_attempts", retry_attempts)
                    if retry_attempts < _PAGINATED_GET_MAX_ATTEMPTS:
                        time.sleep(self._retry_after_seconds(response, body, retry_attempts))
                        continue
                    setattr(self, "_paginated_retry_attempts", 0)
                else:
                    setattr(self, "_paginated_retry_attempts", 0)

                self._raise_for_status(response.status_code, body)

                if response.status_code // 100 != 2:
                    raise ProviderError(
                        f"amoCRM {path} returned {response.status_code}",
                        provider=self.provider.value,
                        status_code=response.status_code,
                        payload=body,
                    )

                if not isinstance(body, dict):
                    raise ProviderError(
                        f"amoCRM {path} вернул не-JSON объект",
                        provider=self.provider.value,
                    )

                embedded = body.get("_embedded") or {}
                items = embedded.get(items_key) or []
                for item in items:
                    if isinstance(item, dict):
                        yield item

                links = body.get("_links") or {}
                next_link = (links.get("next") or {}).get("href")
                if not next_link:
                    url = None
                    current_params = None
                else:
                    url = next_link
                    # next.href уже с query string — не дублируем params.
                    current_params = None

    def _ajax_get(
        self,
        path: str,
        access_token: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Backend-only experimental amoCRM AJAX GET with OAuth bearer token."""
        url = self._account_url(path)
        with httpx.Client(timeout=self._http_timeout) as client:
            last_request_error: httpx.RequestError | None = None
            for attempt in range(1, _PAGINATED_GET_MAX_ATTEMPTS + 1):
                try:
                    self._throttle_api_request()
                    response = client.get(
                        url,
                        params=params,
                        headers={
                            "Authorization": f"Bearer {access_token}",
                            "Accept": "application/json",
                            "X-Requested-With": "XMLHttpRequest",
                            "User-Agent": "code9-analytics/1.0",
                        },
                    )
                except httpx.RequestError as exc:
                    last_request_error = exc
                    if attempt >= _PAGINATED_GET_MAX_ATTEMPTS:
                        raise ProviderError(
                            f"amoCRM AJAX endpoint unreachable after "
                            f"{_PAGINATED_GET_MAX_ATTEMPTS} attempts: "
                            f"{type(exc).__name__}",
                            provider=self.provider.value,
                        ) from None
                    time.sleep(_PAGINATED_GET_RETRY_BASE_SECONDS * (2 ** (attempt - 1)))
                    continue

                if response.status_code == 204:
                    return {}
                try:
                    body: Any = response.json()
                except ValueError:
                    body = {"text": response.text[:500]}
                if (response.status_code == 429 or response.status_code >= 500) and (
                    attempt < _PAGINATED_GET_MAX_ATTEMPTS
                ):
                    time.sleep(self._retry_after_seconds(response, body, attempt))
                    continue
                self._raise_for_status(response.status_code, body)
                if response.status_code // 100 != 2:
                    raise ProviderError(
                        f"amoCRM AJAX endpoint returned {response.status_code}",
                        provider=self.provider.value,
                        status_code=response.status_code,
                        payload={"type": type(body).__name__},
                    )
                return body

        exc_name = type(last_request_error).__name__ if last_request_error else "unknown"
        raise ProviderError(
            f"amoCRM AJAX endpoint unreachable: {exc_name}",
            provider=self.provider.value,
        )

    @staticmethod
    def _timeline_lists(body: Any) -> list[list[Any]]:
        if isinstance(body, list):
            return [body]
        if not isinstance(body, dict):
            return []
        lists: list[list[Any]] = []
        for key in ("items", "events", "timeline", "messages", "notes"):
            value = body.get(key)
            if isinstance(value, list):
                lists.append(value)
        embedded = body.get("_embedded")
        if isinstance(embedded, dict):
            for key in ("items", "events", "timeline", "messages", "notes"):
                value = embedded.get(key)
                if isinstance(value, list):
                    lists.append(value)
        response = body.get("response")
        if isinstance(response, dict):
            lists.extend(AmoCrmConnector._timeline_lists(response))
        return lists

    @staticmethod
    def _message_text(payload: dict[str, Any]) -> str | None:
        for key in ("text", "body", "message_text"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        message = payload.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
        if isinstance(message, dict):
            for key in ("text", "caption", "body"):
                value = message.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        params = payload.get("params")
        if isinstance(params, dict):
            for key in ("text", "message", "body"):
                value = params.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return None

    @staticmethod
    def _is_message_timeline_item(payload: dict[str, Any]) -> bool:
        haystack = " ".join(
            str(payload.get(key) or "")
            for key in ("type", "event_type", "note_type", "action", "entity", "name")
        ).lower()
        if any(part in haystack for part in ("message", "chat", "imbox", "inbox", "mail")):
            return True
        if isinstance(payload.get("message"), (dict, str)):
            return True
        if any(payload.get(key) for key in ("chat_id", "talk_id", "conversation_id", "msgid")):
            return True
        return False

    @staticmethod
    def _timeline_item_id(deal_id: str, payload: dict[str, Any]) -> str:
        for key in ("id", "event_id", "message_id", "msgid", "uuid"):
            value = payload.get(key)
            if value is not None:
                return f"{deal_id}:{value}"
        digest = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()[:24]
        return f"{deal_id}:timeline:{digest}"

    @staticmethod
    def _timeline_chat_id(deal_id: str, payload: dict[str, Any]) -> str:
        for key in ("chat_id", "talk_id", "conversation_id"):
            value = payload.get(key)
            if value is not None:
                return str(value)
        message = payload.get("message")
        if isinstance(message, dict):
            for key in ("chat_id", "conversation_id"):
                value = message.get(key)
                if value is not None:
                    return str(value)
        return f"deal:{deal_id}"

    @staticmethod
    def _timeline_author_kind(payload: dict[str, Any]) -> str:
        direction = str(payload.get("direction") or payload.get("message_type") or "").lower()
        if any(part in direction for part in ("out", "manager", "user")):
            return "user"
        if any(part in direction for part in ("in", "client", "customer")):
            return "client"
        sender = payload.get("sender")
        if isinstance(sender, dict) and sender.get("ref_id"):
            return "user"
        if payload.get("created_by") or payload.get("author_user_id"):
            return "user"
        return "client"

    @staticmethod
    def _timeline_author_user_id(payload: dict[str, Any]) -> str | None:
        for key in ("created_by", "author_user_id", "user_id", "responsible_user_id"):
            value = payload.get(key)
            if value is not None:
                return str(value)
        sender = payload.get("sender")
        if isinstance(sender, dict) and sender.get("ref_id") is not None:
            return str(sender.get("ref_id"))
        return None

    @staticmethod
    def _timeline_channel(payload: dict[str, Any]) -> str | None:
        for key in ("channel", "origin", "source_name", "message_type"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        source = payload.get("source")
        if isinstance(source, dict):
            for key in ("name", "type", "external_id"):
                value = source.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return "amocrm"

    @staticmethod
    def _inbox_chat_items(body: Any) -> list[dict[str, Any]]:
        if isinstance(body, list):
            return [item for item in body if isinstance(item, dict)]
        if not isinstance(body, dict):
            return []
        response = body.get("response")
        if isinstance(response, dict):
            nested = AmoCrmConnector._inbox_chat_items(response)
            if nested:
                return nested
        embedded = body.get("_embedded")
        candidates: list[Any] = []
        for key in ("items", "chats", "talks", "conversations"):
            candidates.append(body.get(key))
            if isinstance(embedded, dict):
                candidates.append(embedded.get(key))
        for candidate in candidates:
            if isinstance(candidate, list):
                return [item for item in candidate if isinstance(item, dict)]
        return []

    @staticmethod
    def _chat_last_message_at(payload: dict[str, Any]) -> Optional[datetime]:
        for key in ("last_message_at", "updated_at", "created_at"):
            parsed = AmoCrmConnector._from_epoch(payload.get(key))
            if parsed is not None:
                return parsed
        message = payload.get("last_message")
        if isinstance(message, dict):
            for key in ("created_at", "timestamp", "date"):
                parsed = AmoCrmConnector._from_epoch(message.get(key))
                if parsed is not None:
                    return parsed
        return None

    @staticmethod
    def _nested_id(payload: dict[str, Any], *paths: str) -> str | None:
        for path in paths:
            current: Any = payload
            for part in path.split("."):
                if not isinstance(current, dict):
                    current = None
                    break
                current = current.get(part)
            if current is not None and current != "":
                return str(current)
        return None

    # ----- OAuth --------------------------------------------------------------

    def oauth_authorize_url(self, state: str, redirect_uri: str) -> str:
        """
        URL для amoCRM OAuth. BE делает 302 на этот URL.

        amoCRM поддерживает ``mode=post_message`` (popup) и ``mode=redirect``.
        Мы используем redirect — popup мешает при embed'е в мобильный браузер.
        """
        if not self._client_id:
            raise ProviderError(
                "AMOCRM_CLIENT_ID не задан. В MVP используйте MOCK_CRM_MODE=true.",
                provider=self.provider.value,
            )
        params = {
            "client_id": self._client_id,
            "state": state,
            "mode": "post_message",
            "redirect_uri": redirect_uri,
        }
        return f"{_AMO_AUTHORIZE_URL}?{urlencode(params)}"

    def exchange_code(self, code: str, redirect_uri: str) -> TokenPair:
        """
        Обмен authorization_code на access+refresh токены.

        Требования:
            * self._client_id / self._client_secret должны быть заполнены.
            * self._subdomain должен быть выставлен (из state Redis'а или из
              ``referer`` query-параметра callback'а).

        Исключения:
            * ``InvalidGrant``  — 400 с hint=invalid_grant (битый code).
            * ``ProviderError`` — всё остальное (сеть, 5xx, невалидный JSON).
        """
        if not self._client_id or not self._client_secret:
            raise ProviderError(
                "AMOCRM_CLIENT_ID / AMOCRM_CLIENT_SECRET не заданы.",
                provider=self.provider.value,
            )
        payload = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        }
        return self._post_token(payload)

    def refresh(self, refresh_token: str) -> TokenPair:
        """
        Обновление access_token по refresh_token.

        amoCRM ротирует refresh_token на каждом вызове — **всегда** берём
        `new_refresh = response.refresh_token`, а не переиспользуем старый.
        Это уже сделано в `_token_pair_from_response`: поле `refresh_token`
        возвращается непосредственно из JSON-ответа.

        При ``InvalidGrant`` (400 + hint=invalid_grant) worker должен
        перевести CrmConnection.status = 'lost_token' и оповестить owner'а.
        """
        if not self._client_id or not self._client_secret:
            raise ProviderError(
                "AMOCRM_CLIENT_ID / AMOCRM_CLIENT_SECRET не заданы.",
                provider=self.provider.value,
            )
        if not refresh_token:
            raise InvalidGrant(
                "Refresh token пустой — нечего обновлять.",
                provider=self.provider.value,
            )
        payload = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        return self._post_token(payload)

    # ----- Account / Audit ----------------------------------------------------

    def fetch_account(self, access_token: str) -> dict[str, Any]:
        """
        GET `/api/v4/account` → info об аккаунте.

        Ответ содержит: ``id`` (int), ``name``, ``subdomain``, ``country``,
        ``currency``, ``created_at``, ``created_by`` и др. Мы сохраняем:

        * ``CrmConnection.external_account_id = str(account.id)``
        * ``CrmConnection.external_domain = f"{account.subdomain}.amocrm.ru"``
        * полный ответ кладём в ``CrmConnection.metadata_json["amo_account"]``
        """
        url = self._api_url("account")
        try:
            with httpx.Client(timeout=self._http_timeout) as client:
                self._throttle_api_request()
                response = client.get(
                    url,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/json",
                        "User-Agent": "code9-analytics/1.0",
                    },
                )
        except httpx.RequestError as exc:
            raise ProviderError(
                f"amoCRM /api/v4/account unreachable: {type(exc).__name__}",
                provider=self.provider.value,
            ) from None

        try:
            body: Any = response.json()
        except ValueError:
            body = {"text": response.text[:500]}

        self._raise_for_status(response.status_code, body)

        if response.status_code // 100 != 2:
            raise ProviderError(
                f"amoCRM /account returned {response.status_code}",
                provider=self.provider.value,
                status_code=response.status_code,
                payload=body,
            )
        if not isinstance(body, dict):
            raise ProviderError(
                "amoCRM /account вернул не-JSON объект",
                provider=self.provider.value,
                payload={"type": type(body).__name__},
            )
        return body

    def audit(self, access_token: str) -> dict[str, Any]:
        """
        Быстрый audit: count leads/contacts/companies/users.

        В Phase 2A не используется — запускается pull job с лимитом и тем
        самым даёт audit_summary. Остаётся как TODO (V1).
        """
        raise NotImplementedError(_V1_NOT_IMPLEMENTED_MSG.format(method="audit"))

    # ----- Fetchers (Phase 2A step 4 / Phase 2B) ------------------------------

    def fetch_deals(
        self,
        access_token: str,
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
        *,
        created_from: Optional[datetime] = None,
        created_to: Optional[datetime] = None,
        pipeline_ids: Optional[list[str]] = None,
    ) -> Iterable[RawDeal]:
        """
        Выгружает сделки (``/api/v4/leads``).

        * ``with=contacts,companies,catalog_elements,source`` → amoCRM вложит
          в ``_embedded`` первичные связи, привязанные товары/элементы списков
          и источник; из contacts/companies берём ``contact_id`` /
          ``company_id``, остальное сохраняется в raw payload.
        * ``since`` → ``filter[updated_at][from]=<unix>``, инкрементальная
          выборка. Без since — полный дамп.
        * ``created_from``/``created_to`` → пользовательский аналитический
          срез по дате создания сделки.
        * ``pipeline_ids`` → выбранные пользователем воронки; пустой список
          означает "все воронки".
        * ``limit`` — отсечка на стороне caller'а (не per-page, а общая).

        Нормализация статусов:

            status_id=142 → 'won'
            status_id=143 → 'lost'
            иначе          → 'open'

        amoCRM не кладёт валюту в лид (она на уровне аккаунта) → ``currency=None``.
        Источник лида (``source``) сохраняется в raw payload как
        ``_embedded.source``; нормализованный source mapping — отдельный слой.
        """
        params: dict[str, Any] = {"with": "contacts,companies,catalog_elements,source"}
        if since is not None:
            params["filter[updated_at][from]"] = self._to_epoch(since)
        if created_from is not None:
            params["filter[created_at][from]"] = self._to_epoch(created_from)
        if created_to is not None:
            params["filter[created_at][to]"] = self._to_epoch(created_to)
        for idx, pipeline_id in enumerate(pipeline_ids or []):
            params[f"filter[pipeline_id][{idx}]"] = str(pipeline_id)

        yielded = 0
        for item in self._paginated_get(
            "leads", access_token, items_key="leads", params=params
        ):
            if limit is not None and yielded >= limit:
                return
            yielded += 1

            status_id = item.get("status_id")
            if status_id == 142:
                status_kind: Optional[str] = "won"
            elif status_id == 143:
                status_kind = "lost"
            else:
                status_kind = "open"

            embedded = item.get("_embedded") or {}
            contacts_list = embedded.get("contacts") or []
            companies_list = embedded.get("companies") or []
            contact_id: Optional[str] = None
            if contacts_list and isinstance(contacts_list[0], dict):
                cid = contacts_list[0].get("id")
                contact_id = str(cid) if cid else None
            company_id: Optional[str] = None
            if companies_list and isinstance(companies_list[0], dict):
                coid = companies_list[0].get("id")
                company_id = str(coid) if coid else None

            responsible_user_id = item.get("responsible_user_id")
            price_raw = item.get("price")
            price_val: Optional[float]
            if isinstance(price_raw, (int, float)):
                price_val = float(price_raw)
            else:
                price_val = None

            yield RawDeal(
                crm_id=str(item.get("id", "")),
                name=item.get("name"),
                price=price_val,
                currency=None,
                status=status_kind,
                pipeline_id=(
                    str(item.get("pipeline_id"))
                    if item.get("pipeline_id") is not None
                    else None
                ),
                stage_id=str(status_id) if status_id is not None else None,
                responsible_user_id=(
                    str(responsible_user_id)
                    if responsible_user_id is not None
                    else None
                ),
                contact_id=contact_id,
                company_id=company_id,
                source=None,
                created_at=self._from_epoch(item.get("created_at")),
                updated_at=self._from_epoch(item.get("updated_at")),
                closed_at=self._from_epoch(item.get("closed_at")),
                raw_payload=item,
            )

    def fetch_contacts(
        self,
        access_token: str,
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> Iterable[RawContact]:
        """
        Выгружает контакты (``/api/v4/contacts``).

        phone / email — из ``custom_fields_values`` (по ``field_code``).
        У одного контакта может быть несколько телефонов — берём первый.
        Компания — первая из ``_embedded.companies`` (если запрошена).
        """
        params: dict[str, Any] = {"with": "companies"}
        if since is not None:
            params["filter[updated_at][from]"] = self._to_epoch(since)

        yielded = 0
        for item in self._paginated_get(
            "contacts", access_token, items_key="contacts", params=params
        ):
            if limit is not None and yielded >= limit:
                return
            yielded += 1

            phone, email = self._extract_phone_email(item.get("custom_fields_values"))
            embedded = item.get("_embedded") or {}
            companies_list = embedded.get("companies") or []
            company_id: Optional[str] = None
            if companies_list and isinstance(companies_list[0], dict):
                coid = companies_list[0].get("id")
                company_id = str(coid) if coid else None

            responsible_user_id = item.get("responsible_user_id")
            yield RawContact(
                crm_id=str(item.get("id", "")),
                name=item.get("name"),
                phone=phone,
                email=email,
                responsible_user_id=(
                    str(responsible_user_id)
                    if responsible_user_id is not None
                    else None
                ),
                company_id=company_id,
                created_at=self._from_epoch(item.get("created_at")),
                updated_at=self._from_epoch(item.get("updated_at")),
                raw_payload=item,
            )

    def fetch_companies(
        self,
        access_token: str,
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> Iterable[RawCompany]:
        """Выгружает компании (``/api/v4/companies``)."""
        params: dict[str, Any] = {}
        if since is not None:
            params["filter[updated_at][from]"] = self._to_epoch(since)

        yielded = 0
        for item in self._paginated_get(
            "companies", access_token, items_key="companies", params=params
        ):
            if limit is not None and yielded >= limit:
                return
            yielded += 1

            custom_fields = item.get("custom_fields_values")
            phone, _email = self._extract_phone_email(custom_fields)
            inn = self._first_custom_field_value(
                custom_fields,
                field_codes={"INN"},
                field_name_contains=("инн", "inn"),
            )
            website = self._first_custom_field_value(
                custom_fields,
                field_codes={"WEB", "SITE", "URL"},
                field_name_contains=("сайт", "site", "web", "url"),
            )
            responsible_user_id = item.get("responsible_user_id")

            yield RawCompany(
                crm_id=str(item.get("id", "")),
                name=item.get("name"),
                inn=inn,
                phone=phone,
                website=website,
                responsible_user_id=(
                    str(responsible_user_id)
                    if responsible_user_id is not None
                    else None
                ),
                created_at=self._from_epoch(item.get("created_at")),
                updated_at=self._from_epoch(item.get("updated_at")),
                raw_payload=item,
            )

    def fetch_pipelines(self, access_token: str) -> Iterable[RawPipeline]:
        """
        Выгружает воронки (``/api/v4/leads/pipelines``).

        amoCRM возвращает воронки со статусами внутри ``_embedded.statuses`` —
        это используется в ``fetch_stages``, который тоже ходит на
        ``/leads/pipelines``, но эмитит статусы, а не воронки.
        """
        for item in self._paginated_get(
            "leads/pipelines", access_token, items_key="pipelines"
        ):
            name = item.get("name") or ""
            yield RawPipeline(
                crm_id=str(item.get("id", "")),
                name=name,
                is_default=bool(item.get("is_main", False)),
                sort_order=item.get("sort"),
                raw_payload=item,
            )

    def fetch_stages(self, access_token: str) -> Iterable[RawStage]:
        """
        Выгружает этапы (amoCRM статусы) всех воронок.

        Отдельного endpoint'а для статусов без привязки к воронке нет —
        мы переиспользуем ``/leads/pipelines`` и эмитим статусы.

        Нормализация ``kind``:

            status_id == 142  → 'won'
            status_id == 143  → 'lost'
            остальные         → 'open' (в amoCRM это все пользовательские этапы)
        """
        for pipeline in self._paginated_get(
            "leads/pipelines", access_token, items_key="pipelines"
        ):
            pipeline_id = str(pipeline.get("id", ""))
            embedded = pipeline.get("_embedded") or {}
            statuses = embedded.get("statuses") or []
            for status in statuses:
                if not isinstance(status, dict):
                    continue
                status_id = status.get("id")
                if status_id == 142:
                    kind: Optional[str] = "won"
                elif status_id == 143:
                    kind = "lost"
                else:
                    kind = "open"
                yield RawStage(
                    crm_id=str(status_id) if status_id is not None else "",
                    pipeline_id=pipeline_id,
                    name=status.get("name") or "",
                    sort_order=status.get("sort"),
                    kind=kind,  # type: ignore[arg-type]
                    color=status.get("color"),
                    raw_payload=status,
                )

    def fetch_users(self, access_token: str) -> Iterable[RawUser]:
        """
        Выгружает пользователей (менеджеров) (``/api/v4/users``).

        Роль определяем из ``rights``:

            ``rights.is_admin=true``  → 'admin'
            ``rights.is_free=true``   → 'free'   (read-only)
            иначе                      → 'user'

        amoCRM не отдаёт флаг «деактивирован» в v4 напрямую — есть косвенный
        ``rights.status_id`` / выпадает из списка. Пока держим is_active=True,
        уточним в Phase 2B через ``GET /users/{id}`` при необходимости.
        """
        for item in self._paginated_get("users", access_token, items_key="users"):
            rights = item.get("rights") if isinstance(item.get("rights"), dict) else {}
            if rights.get("is_admin"):
                role: Optional[str] = "admin"
            elif rights.get("is_free"):
                role = "free"
            else:
                role = "user"
            yield RawUser(
                crm_id=str(item.get("id", "")),
                name=item.get("name"),
                email=item.get("email"),
                role=role,
                is_active=True,
                raw_payload=item,
            )

    def fetch_calls(
        self,
        access_token: str,
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> Iterable[RawCall]:
        raise NotImplementedError(_V1_NOT_IMPLEMENTED_MSG.format(method="fetch_calls"))

    def fetch_messages(
        self,
        access_token: str,
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> Iterable[RawMessage]:
        raise NotImplementedError(_V1_NOT_IMPLEMENTED_MSG.format(method="fetch_messages"))

    def fetch_lead_timeline_messages(
        self,
        access_token: str,
        deal_ids: Iterable[str],
        *,
        created_from: Optional[datetime] = None,
        created_to: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> Iterable[RawMessage]:
        """Experimental import of client messages from lead events_timeline AJAX."""
        yielded = 0
        for deal_id in deal_ids:
            if limit is not None and yielded >= limit:
                return
            params: dict[str, Any] = {}
            if created_from is not None or created_to is not None:
                from_ts = self._to_epoch(created_from) if created_from is not None else 0
                to_ts = (
                    self._to_epoch(created_to)
                    if created_to is not None
                    else self._to_epoch(datetime.now(tz=timezone.utc))
                )
                params["filter[created_at][gte_lte]"] = f"{from_ts}.{to_ts}"
            body = self._ajax_get(
                f"ajax/v3/leads/{deal_id}/events_timeline",
                access_token,
                params=params,
            )
            for items in self._timeline_lists(body):
                for item in items:
                    if limit is not None and yielded >= limit:
                        return
                    if not isinstance(item, dict):
                        continue
                    if not self._is_message_timeline_item(item):
                        continue
                    sent_at = (
                        self._from_epoch(item.get("created_at"))
                        or self._from_epoch(item.get("timestamp"))
                        or self._from_epoch(item.get("msec_timestamp"))
                    )
                    if created_from is not None and sent_at is not None and sent_at < created_from:
                        continue
                    if created_to is not None and sent_at is not None and sent_at > created_to:
                        continue
                    yielded += 1
                    yield RawMessage(
                        crm_id=self._timeline_item_id(str(deal_id), item),
                        chat_id=self._timeline_chat_id(str(deal_id), item),
                        deal_id=str(deal_id),
                        contact_id=None,
                        author_kind=self._timeline_author_kind(item),  # type: ignore[arg-type]
                        author_user_id=self._timeline_author_user_id(item),
                        channel=self._timeline_channel(item),
                        text=self._message_text(item),
                        sent_at=sent_at,
                        raw_payload=item,
                    )

    def fetch_contact_timeline_messages(
        self,
        access_token: str,
        contact_ids: Iterable[str],
        *,
        created_from: Optional[datetime] = None,
        created_to: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> Iterable[RawMessage]:
        """Experimental import of client messages from contact events_timeline AJAX."""
        yielded = 0
        for contact_id in contact_ids:
            if limit is not None and yielded >= limit:
                return
            params: dict[str, Any] = {}
            if created_from is not None or created_to is not None:
                from_ts = self._to_epoch(created_from) if created_from is not None else 0
                to_ts = (
                    self._to_epoch(created_to)
                    if created_to is not None
                    else self._to_epoch(datetime.now(tz=timezone.utc))
                )
                params["filter[created_at][gte_lte]"] = f"{from_ts}.{to_ts}"
            body = self._ajax_get(
                f"ajax/v3/contacts/{contact_id}/events_timeline",
                access_token,
                params=params,
            )
            for items in self._timeline_lists(body):
                for item in items:
                    if limit is not None and yielded >= limit:
                        return
                    if not isinstance(item, dict) or not self._is_message_timeline_item(item):
                        continue
                    sent_at = (
                        self._from_epoch(item.get("created_at"))
                        or self._from_epoch(item.get("timestamp"))
                        or self._from_epoch(item.get("msec_timestamp"))
                    )
                    if created_from is not None and sent_at is not None and sent_at < created_from:
                        continue
                    if created_to is not None and sent_at is not None and sent_at > created_to:
                        continue
                    yielded += 1
                    owner = f"contact:{contact_id}"
                    yield RawMessage(
                        crm_id=self._timeline_item_id(owner, item),
                        chat_id=self._timeline_chat_id(owner, item),
                        deal_id=self._nested_id(item, "lead_id", "entity.lead_id", "message.lead_id"),
                        contact_id=str(contact_id),
                        author_kind=self._timeline_author_kind(item),  # type: ignore[arg-type]
                        author_user_id=self._timeline_author_user_id(item),
                        channel=self._timeline_channel(item),
                        text=self._message_text(item),
                        sent_at=sent_at,
                        raw_payload=item,
                    )

    def fetch_inbox_chats(
        self,
        access_token: str,
        *,
        created_from: Optional[datetime] = None,
        created_to: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> Iterable[dict[str, Any]]:
        """Experimental global inbox chat scan; caller must match chats to scope."""
        yielded = 0
        page = 1
        while True:
            if limit is not None and yielded >= limit:
                return
            body = self._ajax_get(
                "ajax/v4/inbox/list",
                access_token,
                params={
                    "limit": 50,
                    "page": page,
                    "order[sort_by]": "last_message_at",
                    "order[sort_type]": "desc",
                },
            )
            chats = self._inbox_chat_items(body)
            if not chats:
                return
            stop_by_period = False
            for chat in chats:
                last_at = self._chat_last_message_at(chat)
                if created_to is not None and last_at is not None and last_at > created_to:
                    continue
                if created_from is not None and last_at is not None and last_at < created_from:
                    stop_by_period = True
                    continue
                yielded += 1
                yield chat
                if limit is not None and yielded >= limit:
                    return
            if stop_by_period:
                return
            page += 1

    def fetch_tasks(
        self,
        access_token: str,
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> Iterable[RawTask]:
        """Выгружает задачи (``/api/v4/tasks``)."""
        params: dict[str, Any] = {}
        if since is not None:
            params["filter[updated_at][from]"] = self._to_epoch(since)

        yielded = 0
        for item in self._paginated_get("tasks", access_token, items_key="tasks", params=params):
            if limit is not None and yielded >= limit:
                return
            yielded += 1
            entity_type = str(item.get("entity_type") or "")
            entity_id = item.get("entity_id")
            deal_id = str(entity_id) if entity_type in {"leads", "lead"} and entity_id else None
            contact_id = (
                str(entity_id) if entity_type in {"contacts", "contact"} and entity_id else None
            )
            task_type = item.get("task_type_id")
            yield RawTask(
                crm_id=str(item.get("id", "")),
                deal_id=deal_id,
                contact_id=contact_id,
                responsible_user_id=(
                    str(item.get("responsible_user_id"))
                    if item.get("responsible_user_id") is not None
                    else None
                ),
                kind=str(task_type) if task_type is not None else None,
                text=item.get("text"),
                is_completed=bool(item.get("is_completed")),
                due_at=self._from_epoch(item.get("complete_till")),
                completed_at=(
                    self._from_epoch(item.get("updated_at")) if item.get("is_completed") else None
                ),
                created_at=self._from_epoch(item.get("created_at")),
                raw_payload=item,
            )

    def fetch_notes(
        self,
        access_token: str,
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> Iterable[RawNote]:
        """Выгружает notes/timeline по сделкам (``/api/v4/leads/notes``)."""
        params: dict[str, Any] = {}
        if since is not None:
            params["filter[updated_at][from]"] = self._to_epoch(since)

        yielded = 0
        for item in self._paginated_get(
            "leads/notes", access_token, items_key="notes", params=params
        ):
            if limit is not None and yielded >= limit:
                return
            yielded += 1
            note_params = item.get("params") if isinstance(item.get("params"), dict) else {}
            body = (
                note_params.get("text")
                or note_params.get("comment")
                or note_params.get("message")
                or note_params.get("content")
                or item.get("text")
            )
            entity_id = item.get("entity_id")
            yield RawNote(
                crm_id=str(item.get("id", "")),
                deal_id=str(entity_id) if entity_id is not None else None,
                contact_id=None,
                author_user_id=(
                    str(item.get("created_by")) if item.get("created_by") is not None else None
                ),
                body=str(body) if body is not None else None,
                created_at=self._from_epoch(item.get("created_at")),
                raw_payload=item,
            )

    def fetch_events(
        self,
        access_token: str,
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> Iterable[RawEvent]:
        """Выгружает события amoCRM history (``/api/v4/events``)."""
        params: dict[str, Any] = {}
        if since is not None:
            params["filter[created_at][from]"] = self._to_epoch(since)

        yielded = 0
        for item in self._paginated_get(
            "events", access_token, items_key="events", params=params
        ):
            if limit is not None and yielded >= limit:
                return
            yielded += 1
            entity_id = item.get("entity_id")
            created_by = item.get("created_by")
            yield RawEvent(
                crm_id=str(item.get("id", "")),
                entity_type=str(item.get("entity_type")) if item.get("entity_type") else None,
                entity_id=str(entity_id) if entity_id is not None else None,
                event_type=str(item.get("type")) if item.get("type") else None,
                created_by=str(created_by) if created_by is not None else None,
                created_at=self._from_epoch(item.get("created_at")),
                raw_payload=item,
            )

    def fetch_products(
        self,
        access_token: str,
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> Iterable[RawProduct]:
        """Выгружает элементы catalog/list API как товары/услуги/списки."""
        yielded = 0
        for catalog in self._paginated_get("catalogs", access_token, items_key="catalogs"):
            catalog_id = catalog.get("id")
            if catalog_id is None:
                continue
            params: dict[str, Any] = {}
            if since is not None:
                params["filter[updated_at][from]"] = self._to_epoch(since)
            for item in self._paginated_get(
                f"catalogs/{catalog_id}/elements",
                access_token,
                items_key="elements",
                params=params,
            ):
                if limit is not None and yielded >= limit:
                    return
                yielded += 1
                item_id = item.get("id")
                if item_id is None:
                    continue
                raw_payload = {**item, "_code9_catalog": catalog}
                price = item.get("price")
                if not isinstance(price, (int, float)):
                    price = self._first_custom_field_value(
                        item.get("custom_fields_values"),
                        field_codes={"PRICE"},
                        field_name_contains=("цена", "price", "стоимость"),
                    )
                try:
                    normalized_price = float(price) if price is not None else None
                except (TypeError, ValueError):
                    normalized_price = None
                yield RawProduct(
                    crm_id=f"{catalog_id}:{item_id}",
                    name=item.get("name"),
                    price=normalized_price,
                    currency=None,
                    raw_payload=raw_payload,
                )

    def fetch_custom_fields(
        self,
        access_token: str,
        entity_types: Optional[list[str]] = None,
    ) -> Iterable[RawCustomField]:
        """Выгружает описания custom fields для основных amoCRM сущностей."""
        requested = entity_types or ["leads", "contacts", "companies", "catalogs"]
        for entity_type in requested:
            if entity_type == "catalogs":
                try:
                    catalogs = list(
                        self._paginated_get("catalogs", access_token, items_key="catalogs")
                    )
                except ProviderError:
                    catalogs = []
                for catalog in catalogs:
                    catalog_id = catalog.get("id")
                    if catalog_id is None:
                        continue
                    try:
                        fields = self._paginated_get(
                            f"catalogs/{catalog_id}/custom_fields",
                            access_token,
                            items_key="custom_fields",
                        )
                    except ProviderError:
                        continue
                    for item in fields:
                        field_id = item.get("id")
                        if field_id is None:
                            continue
                        raw_payload = {**item, "_code9_catalog": catalog}
                        yield RawCustomField(
                            crm_id=f"{catalog_id}:{field_id}",
                            entity_type="product",
                            name=item.get("name"),
                            code=item.get("code"),
                            field_type=item.get("type"),
                            raw_payload=raw_payload,
                        )
                continue

            endpoint_map = {
                "leads": ("deal", "leads/custom_fields"),
                "deals": ("deal", "leads/custom_fields"),
                "contacts": ("contact", "contacts/custom_fields"),
                "companies": ("company", "companies/custom_fields"),
                "tasks": ("task", "tasks/custom_fields"),
            }
            mapped = endpoint_map.get(entity_type)
            if mapped is None:
                continue
            normalized_entity, endpoint = mapped
            try:
                items = self._paginated_get(
                    endpoint,
                    access_token,
                    items_key="custom_fields",
                )
                for item in items:
                    field_id = item.get("id")
                    if field_id is None:
                        continue
                    yield RawCustomField(
                        crm_id=str(field_id),
                        entity_type=normalized_entity,
                        name=item.get("name"),
                        code=item.get("code"),
                        field_type=item.get("type"),
                        raw_payload=item,
                    )
            except ProviderError:
                continue

    # ----- служебное ----------------------------------------------------------

    def _raise_for_status(self, status_code: int, body: Any) -> None:
        """
        HTTP-код amoCRM → доменное исключение.

        401                                  → TokenExpired
        400 + hint=invalid_grant              → InvalidGrant
        429                                  → RateLimited (с retry_after)
        >=500                                 → ProviderError
        Всё остальное — no-op; caller решает, что делать с 2xx/3xx/прочими 4xx.
        """
        if status_code == 401:
            raise TokenExpired(
                "Access token rejected (401)",
                provider=self.provider.value,
                payload=body,
            )
        if status_code == 400 and isinstance(body, dict) and body.get("hint") == "invalid_grant":
            raise InvalidGrant(
                "Refresh token rejected",
                provider=self.provider.value,
                payload=body,
            )
        if status_code == 429:
            retry_after = None
            if isinstance(body, dict):
                retry_after = body.get("retry_after")
            raise RateLimited(
                "Rate limited by amoCRM",
                provider=self.provider.value,
                retry_after_seconds=retry_after,
                payload=body,
            )
        if status_code >= 500:
            raise ProviderError(
                f"amoCRM {status_code}",
                provider=self.provider.value,
                status_code=status_code,
                payload=body,
            )


__all__ = ["AmoCrmConnector"]
