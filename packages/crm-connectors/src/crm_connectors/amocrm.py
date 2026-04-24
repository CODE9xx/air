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
* остальные `fetch_*`    — NotImplementedError, Phase 2B/2C (calls, chats,
  tasks, notes, companies) — см. ``docs/api/CONTRACT.md §CRM``.

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
    RawDeal,
    RawMessage,
    RawNote,
    RawPipeline,
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

        * ``with=contacts,companies`` → amoCRM вложит в ``_embedded``
          первичные связи; из них берём ``contact_id`` / ``company_id``.
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
        Источник лида (``source``) — Phase 2B (``/leads/sources``).
        """
        params: dict[str, Any] = {"with": "contacts,companies"}
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
        """Phase 2B — companies pull. В Phase 2A не включён."""
        raise NotImplementedError(_V1_NOT_IMPLEMENTED_MSG.format(method="fetch_companies"))

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

    def fetch_tasks(
        self,
        access_token: str,
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> Iterable[RawTask]:
        raise NotImplementedError(_V1_NOT_IMPLEMENTED_MSG.format(method="fetch_tasks"))

    def fetch_notes(
        self,
        access_token: str,
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> Iterable[RawNote]:
        raise NotImplementedError(_V1_NOT_IMPLEMENTED_MSG.format(method="fetch_notes"))

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
