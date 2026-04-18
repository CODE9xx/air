"""
AmoCrmConnector — скелет реального коннектора к amoCRM.

В MVP все реальные `fetch_*` — **NotImplementedError**. Задача этого класса:
- держать контракт `CRMConnector` компилируемым и импортируемым;
- содержать точки расширения для V1 (реальный HTTP через `httpx`);
- в MOCK-режиме factory возвращает `MockCRMConnector`, а не этот класс.

См. `docs/api/CONTRACT.md` раздел «CRM Connections / oauth/amocrm/*».
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional
from urllib.parse import urlencode

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


class AmoCrmConnector(CRMConnector):
    """
    Реальный клиент amoCRM. В MVP — **skeleton**.

    Поля конструктора:
        client_id, client_secret: OAuth-приложение amoCRM. Читается из env
            (`AMOCRM_CLIENT_ID`, `AMOCRM_CLIENT_SECRET`) в обёртке worker'а.
        http_timeout: таймаут httpx-клиента.

    Все `fetch_*` методы в V1 буду реализованы через `httpx.Client` и парсинг
    amoCRM API v4. Пока они raise NotImplementedError с понятным сообщением.
    """

    provider: Provider = Provider.AMOCRM

    def __init__(
        self,
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
        http_timeout: float = 30.0,
        subdomain: str | None = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._http_timeout = http_timeout
        # subdomain нужен для token exchange (`https://{subdomain}.amocrm.ru/...`).
        self._subdomain = subdomain

    # ----- OAuth --------------------------------------------------------------

    def oauth_authorize_url(self, state: str, redirect_uri: str) -> str:
        """
        Возвращает URL для amoCRM OAuth. Реальный редирект — ответственность BE
        (endpoint `/crm/oauth/amocrm/start` делает 302 на этот URL).
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
        Реальный exchange — POST на `https://{subdomain}.amocrm.ru/oauth2/access_token`.
        В MVP не реализован: TokenPair создаётся MockCRMConnector.
        """
        raise NotImplementedError(_V1_NOT_IMPLEMENTED_MSG.format(method="exchange_code"))

    def refresh(self, refresh_token: str) -> TokenPair:
        """
        Реальный refresh — тот же endpoint, `grant_type=refresh_token`.
        При 401 / `invalid_grant` — raise `InvalidGrant`, worker переведёт
        подключение в `lost_token`.
        """
        raise NotImplementedError(_V1_NOT_IMPLEMENTED_MSG.format(method="refresh"))

    # ----- Account / Audit ----------------------------------------------------

    def fetch_account(self, access_token: str) -> dict[str, Any]:
        """GET `/api/v4/account`."""
        raise NotImplementedError(_V1_NOT_IMPLEMENTED_MSG.format(method="fetch_account"))

    def audit(self, access_token: str) -> dict[str, Any]:
        """
        Цикл `count`-запросов по `/api/v4/leads`, `/contacts`, `/companies`, ...
        Использует параметр `limit=1` + чтение `_total_items` из ответа.
        """
        raise NotImplementedError(_V1_NOT_IMPLEMENTED_MSG.format(method="audit"))

    # ----- Fetchers -----------------------------------------------------------

    def fetch_deals(
        self,
        access_token: str,
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> Iterable[RawDeal]:
        raise NotImplementedError(_V1_NOT_IMPLEMENTED_MSG.format(method="fetch_deals"))

    def fetch_contacts(
        self,
        access_token: str,
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> Iterable[RawContact]:
        raise NotImplementedError(_V1_NOT_IMPLEMENTED_MSG.format(method="fetch_contacts"))

    def fetch_companies(
        self,
        access_token: str,
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> Iterable[RawCompany]:
        raise NotImplementedError(_V1_NOT_IMPLEMENTED_MSG.format(method="fetch_companies"))

    def fetch_pipelines(self, access_token: str) -> Iterable[RawPipeline]:
        raise NotImplementedError(_V1_NOT_IMPLEMENTED_MSG.format(method="fetch_pipelines"))

    def fetch_stages(self, access_token: str) -> Iterable[RawStage]:
        raise NotImplementedError(_V1_NOT_IMPLEMENTED_MSG.format(method="fetch_stages"))

    def fetch_users(self, access_token: str) -> Iterable[RawUser]:
        raise NotImplementedError(_V1_NOT_IMPLEMENTED_MSG.format(method="fetch_users"))

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

    # ----- служебное (V1) -----------------------------------------------------

    def _raise_for_status(self, status_code: int, body: Any) -> None:
        """
        Переводит HTTP-ответ amoCRM в исключения нашего слоя.
        Используется будущей реальной реализацией (V1). Вынесено сюда, чтобы
        все коннекторы имели единое поведение по 401/429/5xx.
        """
        if status_code == 401:
            # amoCRM не различает expired-vs-revoked в теле: оба — 401.
            # Worker сначала попробует refresh, при 400 invalid_grant — lost_token.
            raise TokenExpired("Access token rejected (401)", provider=self.provider.value, payload=body)
        if status_code == 400 and isinstance(body, dict) and body.get("hint") == "invalid_grant":
            raise InvalidGrant("Refresh token rejected", provider=self.provider.value, payload=body)
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
