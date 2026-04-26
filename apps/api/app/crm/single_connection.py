"""Helpers for the product rule: one CRM connection per workspace."""
from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CrmConnection


async def get_existing_crm_connection(
    session: AsyncSession,
    workspace_id: uuid.UUID,
) -> CrmConnection | None:
    """Return the first non-deleted CRM connection for this workspace."""
    row = await session.execute(
        select(CrmConnection)
        .where(CrmConnection.workspace_id == workspace_id)
        .where(CrmConnection.status != "deleted")
        .order_by(CrmConnection.created_at.asc())
        .limit(1)
    )
    return row.scalar_one_or_none()


def raise_single_crm_conflict(connection: CrmConnection) -> None:
    """Raise a stable API error when a workspace already has a CRM."""
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "error": {
                "code": "crm_connection_exists",
                "message": (
                    "В этом кабинете уже есть CRM-подключение. "
                    "Один кабинет поддерживает одно CRM-подключение."
                ),
                "connection_id": str(connection.id),
                "provider": connection.provider,
                "status": connection.status,
            }
        },
    )


async def ensure_no_existing_crm_connection(
    session: AsyncSession,
    workspace_id: uuid.UUID,
) -> None:
    existing = await get_existing_crm_connection(session, workspace_id)
    if existing is not None:
        raise_single_crm_conflict(existing)
