"""Workspace endpoints."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, get_current_workspace
from app.core.db import get_session
from app.db.models import User, Workspace, WorkspaceMember

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


def _serialize(ws: Workspace, role: str | None = None) -> dict[str, Any]:
    return {
        "id": str(ws.id),
        "name": ws.name,
        "slug": ws.slug,
        "locale": ws.locale,
        "industry": ws.industry,
        "status": ws.status,
        "role": role,
        "created_at": ws.created_at.isoformat() if ws.created_at else None,
    }


@router.get("")
async def list_workspaces(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(WorkspaceMember, Workspace)
            .join(Workspace, Workspace.id == WorkspaceMember.workspace_id)
            .where(WorkspaceMember.user_id == user.id)
            .where(Workspace.status != "deleted")
        )
    ).all()
    return [_serialize(ws, role=m.role) for (m, ws) in rows]


@router.get("/current")
async def current_workspace(
    ws: Workspace = Depends(get_current_workspace),
) -> dict[str, Any]:
    return _serialize(ws, role="owner")


@router.get("/{workspace_id}")
async def get_workspace(
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    row = (
        await session.execute(
            select(WorkspaceMember, Workspace)
            .join(Workspace, Workspace.id == WorkspaceMember.workspace_id)
            .where(WorkspaceMember.user_id == user.id)
            .where(Workspace.id == workspace_id)
        )
    ).first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Workspace not found"}},
        )
    m, ws = row
    return _serialize(ws, role=m.role)


@router.get("/{workspace_id}/members")
async def list_members(
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    # Убеждаемся, что user — member.
    is_member = (
        await session.execute(
            select(WorkspaceMember)
            .where(WorkspaceMember.workspace_id == workspace_id)
            .where(WorkspaceMember.user_id == user.id)
        )
    ).scalar_one_or_none()
    if not is_member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "forbidden", "message": "Not a member"}},
        )

    rows = (
        await session.execute(
            select(WorkspaceMember, User)
            .join(User, User.id == WorkspaceMember.user_id)
            .where(WorkspaceMember.workspace_id == workspace_id)
        )
    ).all()
    return [
        {
            "id": str(m.id),
            "user_id": str(u.id),
            "email": u.email,
            "display_name": u.display_name,
            "role": m.role,
            "accepted_at": m.accepted_at.isoformat() if m.accepted_at else None,
        }
        for (m, u) in rows
    ]
