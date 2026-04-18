"""Notifications endpoints."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, get_current_workspace
from app.core.db import get_session
from app.db.models import Notification, User, Workspace

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
async def list_notifications(
    only_unread: bool = False,
    user: User = Depends(get_current_user),
    ws: Workspace = Depends(get_current_workspace),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    q = select(Notification).where(Notification.workspace_id == ws.id)
    if only_unread:
        q = q.where(Notification.read_at.is_(None))
    q = q.order_by(Notification.created_at.desc()).limit(200)
    rows = (await session.execute(q)).scalars().all()
    return [
        {
            "id": str(n.id),
            "kind": n.kind,
            "title": n.title,
            "body": n.body,
            "metadata": n.metadata_json or {},
            "read_at": n.read_at.isoformat() if n.read_at else None,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        for n in rows
    ]


@router.post("/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read(
    notification_id: uuid.UUID,
    user: User = Depends(get_current_user),
    ws: Workspace = Depends(get_current_workspace),
    session: AsyncSession = Depends(get_session),
) -> Response:
    row = (
        await session.execute(
            select(Notification)
            .where(Notification.id == notification_id)
            .where(Notification.workspace_id == ws.id)
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Notification not found"}},
        )
    if row.read_at is None:
        row.read_at = datetime.now(timezone.utc)
        await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
