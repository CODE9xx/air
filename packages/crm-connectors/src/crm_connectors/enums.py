"""
Enum-значения CRM-провайдеров и статусов подключения.

Синхронизировано с `docs/db/SCHEMA.md` — enum `crm_connection.provider` и
`crm_connection.status`. Если потребуется изменить — CR в
`docs/architecture/CHANGE_REQUESTS.md` (owner schema: LEAD+DW).
"""

from __future__ import annotations

from enum import Enum


class Provider(str, Enum):
    """Провайдер CRM. Значения совпадают с колонкой `crm_connections.provider`."""

    AMOCRM = "amocrm"
    KOMMO = "kommo"
    BITRIX24 = "bitrix24"
    # MOCK — «виртуальный» провайдер, используется ТОЛЬКО в MOCK_CRM_MODE.
    # В БД всё равно пишется реальный provider (amocrm/kommo/bitrix24),
    # а факт мока — в crm_connections.metadata.is_mock=true.
    MOCK = "mock"


class ConnectionStatus(str, Enum):
    """Статус подключения. Синхронизирован с CHECK на `crm_connections.status`."""

    PENDING = "pending"
    CONNECTING = "connecting"
    ACTIVE = "active"
    PAUSED = "paused"
    LOST_TOKEN = "lost_token"
    DELETING = "deleting"
    DELETED = "deleted"
    ERROR = "error"


__all__ = ["Provider", "ConnectionStatus"]
