"""
Базовый контракт `CRMConnector` (Protocol) и набор `Raw*` dataclass'ов
для нормализации данных на стороне worker'а (см. `apps/worker/jobs/crm.py`).

Принципы:
- `Raw*` хранят минимум структурированных полей + `raw_payload` с полным
  оригинальным ответом провайдера. В БД (`tenant.raw_*`) кладётся `raw_payload`,
  а нормализация (`tenant.deals`, `tenant.contacts`, ...) делается отдельным
  job'ом `normalize_tenant_data`.
- Все `crm_id` — строки (даже если провайдер возвращает int).
- Денежные суммы — храним как есть в `price` (float), нормализатор переведёт в
  `price_cents: BIGINT`.
- Времена — timezone-aware `datetime` (UTC).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, Literal, Optional, Protocol, runtime_checkable

from .enums import Provider

# ---------------------------------------------------------------------------
# OAuth / токены
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TokenPair:
    """
    Пара токенов, полученная от провайдера.

    `raw` — оригинальный JSON ответа провайдера (для отладки в worker'е).
    Никогда не логировать целиком — там лежат `access_token` и `refresh_token`.
    """

    access_token: str
    refresh_token: str
    expires_at: datetime
    raw: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Raw-сущности (то, что коннектор возвращает worker'у до нормализации)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RawDeal:
    """Сделка."""

    crm_id: str
    name: Optional[str]
    price: Optional[float]
    currency: Optional[str]
    status: Optional[str]  # 'open' | 'won' | 'lost' | <provider-specific>
    pipeline_id: Optional[str]
    stage_id: Optional[str]
    responsible_user_id: Optional[str]
    contact_id: Optional[str] = None
    company_id: Optional[str] = None
    source: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RawContact:
    """Контакт."""

    crm_id: str
    name: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    responsible_user_id: Optional[str]
    company_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RawCompany:
    """Компания (юр. лицо)."""

    crm_id: str
    name: Optional[str]
    inn: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    responsible_user_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RawPipeline:
    """Воронка."""

    crm_id: str
    name: str
    is_default: bool = False
    sort_order: Optional[int] = None
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RawStage:
    """Этап воронки."""

    crm_id: str
    pipeline_id: str
    name: str
    sort_order: Optional[int] = None
    kind: Optional[Literal["open", "won", "lost"]] = None
    color: Optional[str] = None
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RawUser:
    """Пользователь CRM (менеджер)."""

    crm_id: str
    name: Optional[str]
    email: Optional[str]
    role: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RawCall:
    """Звонок (телефония, интегрированная в CRM)."""

    crm_id: str
    deal_id: Optional[str]
    contact_id: Optional[str]
    user_id: Optional[str]
    direction: Literal["in", "out"]
    phone: Optional[str]
    duration_seconds: Optional[int]
    result: Optional[str] = None
    recording_url: Optional[str] = None
    created_at: Optional[datetime] = None
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RawMessage:
    """
    Сообщение (чат / мессенджер).

    `chat_id` — id переписки (не сделки). `author_kind` — `user` (менеджер),
    `client` (клиент) или `system` (бот / шаблонные ответы).
    """

    crm_id: str
    chat_id: Optional[str]
    deal_id: Optional[str]
    contact_id: Optional[str]
    author_kind: Literal["user", "client", "system"]
    author_user_id: Optional[str]
    channel: Optional[str]  # 'whatsapp' | 'telegram' | 'site' | 'email' | ...
    text: Optional[str]
    sent_at: Optional[datetime] = None
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RawTask:
    """Задача."""

    crm_id: str
    deal_id: Optional[str]
    contact_id: Optional[str]
    responsible_user_id: Optional[str]
    kind: Optional[str]  # 'call' | 'meeting' | 'follow_up' | ...
    text: Optional[str]
    is_completed: bool = False
    due_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RawNote:
    """Заметка / комментарий."""

    crm_id: str
    deal_id: Optional[str]
    contact_id: Optional[str]
    author_user_id: Optional[str]
    body: Optional[str]
    created_at: Optional[datetime] = None
    raw_payload: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Контракт коннектора
# ---------------------------------------------------------------------------


@runtime_checkable
class CRMConnector(Protocol):
    """
    Единый контракт для всех CRM-провайдеров.

    Реализации:
    - `MockCRMConnector` — основной для MVP (читает фикстуры).
    - `AmoCrmConnector` — реальный (skeleton, реальные fetch_* — V1).
    - `KommoConnector`, `Bitrix24Connector` — placeholder для V2.

    Все методы — синхронные. Worker (`apps/worker`) на RQ — синхронный пул,
    httpx используется в sync-режиме.
    """

    provider: Provider

    # --- OAuth -----------------------------------------------------------------
    def oauth_authorize_url(self, state: str, redirect_uri: str) -> str:
        """Возвращает URL, на который надо редиректнуть пользователя."""
        ...

    def exchange_code(self, code: str, redirect_uri: str) -> TokenPair:
        """Обменивает authorization-code на пару токенов."""
        ...

    def refresh(self, refresh_token: str) -> TokenPair:
        """Обновляет пару токенов по refresh_token."""
        ...

    # --- Account metadata ------------------------------------------------------
    def fetch_account(self, access_token: str) -> dict[str, Any]:
        """
        Возвращает информацию об аккаунте провайдера:
        ``{"id", "name", "subdomain", "country", ...}``.
        """
        ...

    # --- Audit (только счётчики) -----------------------------------------------
    def audit(self, access_token: str) -> dict[str, Any]:
        """
        Возвращает summary с счётчиками сущностей (без выгрузки данных).
        Используется для пред-просмотра объёма перед полным sync.
        """
        ...

    # --- Trial-friendly fetchers -----------------------------------------------
    def fetch_deals(
        self,
        access_token: str,
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
        *,
        created_from: Optional[datetime] = None,
        created_to: Optional[datetime] = None,
        pipeline_ids: Optional[list[str]] = None,
    ) -> Iterable[RawDeal]: ...

    def fetch_contacts(
        self,
        access_token: str,
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> Iterable[RawContact]: ...

    def fetch_companies(
        self,
        access_token: str,
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> Iterable[RawCompany]: ...

    def fetch_pipelines(self, access_token: str) -> Iterable[RawPipeline]: ...

    def fetch_stages(self, access_token: str) -> Iterable[RawStage]: ...

    def fetch_users(self, access_token: str) -> Iterable[RawUser]: ...

    def fetch_calls(
        self,
        access_token: str,
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> Iterable[RawCall]: ...

    def fetch_messages(
        self,
        access_token: str,
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> Iterable[RawMessage]: ...

    def fetch_tasks(
        self,
        access_token: str,
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> Iterable[RawTask]: ...

    def fetch_notes(
        self,
        access_token: str,
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> Iterable[RawNote]: ...


__all__ = [
    "CRMConnector",
    "TokenPair",
    "RawDeal",
    "RawContact",
    "RawCompany",
    "RawPipeline",
    "RawStage",
    "RawUser",
    "RawCall",
    "RawMessage",
    "RawTask",
    "RawNote",
]
