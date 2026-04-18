"""
Bitrix24Connector — placeholder для V2.

Bitrix24 REST отличается от amoCRM API сильнее — свой OAuth-flow, другие имена
сущностей. В V2 сделаем отдельную реализацию от Protocol напрямую.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Optional

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

_V2_NOT_IMPLEMENTED_MSG = (
    "Bitrix24Connector.{method}: Bitrix24-интеграция планируется в V2. "
    "См. docs/product/ROADMAP.md."
)


class Bitrix24Connector(CRMConnector):
    """Заглушка до V2. В MVP — недостижима через factory (только mock)."""

    provider: Provider = Provider.BITRIX24

    def oauth_authorize_url(self, state: str, redirect_uri: str) -> str:
        raise NotImplementedError(_V2_NOT_IMPLEMENTED_MSG.format(method="oauth_authorize_url"))

    def exchange_code(self, code: str, redirect_uri: str) -> TokenPair:
        raise NotImplementedError(_V2_NOT_IMPLEMENTED_MSG.format(method="exchange_code"))

    def refresh(self, refresh_token: str) -> TokenPair:
        raise NotImplementedError(_V2_NOT_IMPLEMENTED_MSG.format(method="refresh"))

    def fetch_account(self, access_token: str) -> dict[str, Any]:
        raise NotImplementedError(_V2_NOT_IMPLEMENTED_MSG.format(method="fetch_account"))

    def audit(self, access_token: str) -> dict[str, Any]:
        raise NotImplementedError(_V2_NOT_IMPLEMENTED_MSG.format(method="audit"))

    def fetch_deals(self, access_token: str, since: Optional[datetime] = None, limit: Optional[int] = None) -> Iterable[RawDeal]:
        raise NotImplementedError(_V2_NOT_IMPLEMENTED_MSG.format(method="fetch_deals"))

    def fetch_contacts(self, access_token: str, since: Optional[datetime] = None, limit: Optional[int] = None) -> Iterable[RawContact]:
        raise NotImplementedError(_V2_NOT_IMPLEMENTED_MSG.format(method="fetch_contacts"))

    def fetch_companies(self, access_token: str, since: Optional[datetime] = None, limit: Optional[int] = None) -> Iterable[RawCompany]:
        raise NotImplementedError(_V2_NOT_IMPLEMENTED_MSG.format(method="fetch_companies"))

    def fetch_pipelines(self, access_token: str) -> Iterable[RawPipeline]:
        raise NotImplementedError(_V2_NOT_IMPLEMENTED_MSG.format(method="fetch_pipelines"))

    def fetch_stages(self, access_token: str) -> Iterable[RawStage]:
        raise NotImplementedError(_V2_NOT_IMPLEMENTED_MSG.format(method="fetch_stages"))

    def fetch_users(self, access_token: str) -> Iterable[RawUser]:
        raise NotImplementedError(_V2_NOT_IMPLEMENTED_MSG.format(method="fetch_users"))

    def fetch_calls(self, access_token: str, since: Optional[datetime] = None, limit: Optional[int] = None) -> Iterable[RawCall]:
        raise NotImplementedError(_V2_NOT_IMPLEMENTED_MSG.format(method="fetch_calls"))

    def fetch_messages(self, access_token: str, since: Optional[datetime] = None, limit: Optional[int] = None) -> Iterable[RawMessage]:
        raise NotImplementedError(_V2_NOT_IMPLEMENTED_MSG.format(method="fetch_messages"))

    def fetch_tasks(self, access_token: str, since: Optional[datetime] = None, limit: Optional[int] = None) -> Iterable[RawTask]:
        raise NotImplementedError(_V2_NOT_IMPLEMENTED_MSG.format(method="fetch_tasks"))

    def fetch_notes(self, access_token: str, since: Optional[datetime] = None, limit: Optional[int] = None) -> Iterable[RawNote]:
        raise NotImplementedError(_V2_NOT_IMPLEMENTED_MSG.format(method="fetch_notes"))


__all__ = ["Bitrix24Connector"]
