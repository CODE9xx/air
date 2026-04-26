"""
CODE9 shared Python types.

Пока — тонкие TypedDict'ы для enum-значений, которые API и worker могут
импортировать без круговых зависимостей.
"""
from __future__ import annotations

from typing import Literal, TypedDict

# Провайдеры CRM.
CrmProviderT = Literal["amocrm", "kommo", "bitrix24"]

# Статусы подключения.
CrmConnectionStatusT = Literal[
    "pending", "connecting", "active", "paused",
    "lost_token", "deleting", "deleted", "error",
]

# Роли workspace.
WorkspaceRoleT = Literal["owner", "admin", "analyst", "viewer"]

# Job queues.
JobQueueT = Literal["crm", "export", "audit", "ai", "retention", "billing"]


class TokenPair(TypedDict, total=False):
    """OAuth-ответ (CRM provider). `expires_in` — секунды."""

    access_token: str
    refresh_token: str
    expires_in: int


class JobPayload(TypedDict, total=False):
    """Универсальный payload для enqueue jobs."""

    connection_id: str
    workspace_id: str
    deletion_request_id: str
    job_id: str
