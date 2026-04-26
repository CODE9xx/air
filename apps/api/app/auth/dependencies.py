"""
FastAPI dependencies: `get_current_user`, `get_current_workspace`, `require_role`.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Iterable

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.security import decode_token
from app.db.models import AdminSupportSession, AdminUser, User, Workspace, WorkspaceMember


def _extract_bearer(request: Request) -> str | None:
    """Достаёт токен из Authorization header."""
    auth = request.headers.get("Authorization") or request.headers.get("authorization")
    if not auth:
        return None
    parts = auth.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip()


def _unauth(message: str = "Unauthorized") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error": {"code": "unauthorized", "message": message}},
    )


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> User:
    """Парсит Bearer JWT (scope=user), проверяет существование пользователя."""
    token = _extract_bearer(request)
    if not token:
        raise _unauth("Missing Authorization header")
    payload = decode_token(token, scope="user")
    if not payload:
        raise _unauth("Invalid or expired token")
    sub = payload.get("sub")
    if not sub:
        raise _unauth("Token has no subject")
    try:
        user_uuid = uuid.UUID(sub)
    except Exception:
        raise _unauth("Bad subject")
    user = (
        await session.execute(select(User).where(User.id == user_uuid))
    ).scalar_one_or_none()
    if not user or user.status != "active":
        raise _unauth("User not found or inactive")
    support_session_id = payload.get("support_session_id")
    if support_session_id:
        try:
            support_uuid = uuid.UUID(str(support_session_id))
        except Exception:
            raise _unauth("Bad support session")
        support_session = (
            await session.execute(
                select(AdminSupportSession)
                .where(AdminSupportSession.id == support_uuid)
                .where(AdminSupportSession.ended_at.is_(None))
                .where(AdminSupportSession.expires_at > datetime.now(timezone.utc))
            )
        ).scalar_one_or_none()
        if support_session is None:
            raise _unauth("Support session expired")
    return user


async def get_current_admin(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> AdminUser:
    """Парсит Bearer JWT (scope=admin)."""
    token = _extract_bearer(request)
    if not token:
        raise _unauth("Missing Authorization header")
    payload = decode_token(token, scope="admin")
    if not payload:
        raise _unauth("Invalid or expired admin token")
    sub = payload.get("sub")
    if not sub:
        raise _unauth("Token has no subject")
    try:
        admin_uuid = uuid.UUID(sub)
    except Exception:
        raise _unauth("Bad subject")
    admin = (
        await session.execute(select(AdminUser).where(AdminUser.id == admin_uuid))
    ).scalar_one_or_none()
    if not admin or admin.status != "active":
        raise _unauth("Admin not found or inactive")
    return admin


def require_admin_role(*allowed: str):
    """Admin-role check (`superadmin`, `support`, `analyst`)."""

    async def dep(admin: AdminUser = Depends(get_current_admin)) -> AdminUser:
        if allowed and admin.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": {"code": "forbidden", "message": "Insufficient admin role"}},
            )
        return admin

    return dep


async def get_current_workspace(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Workspace:
    """
    Текущий workspace пользователя (в MVP — тот, где он owner).

    В V1 — поддержка multi-workspace через активный X-Workspace-Id header.
    """
    result = await session.execute(
        select(Workspace)
        .where(Workspace.owner_user_id == user.id)
        .where(Workspace.status != "deleted")
        .order_by(Workspace.created_at.asc())
        .limit(1)
    )
    ws = result.scalar_one_or_none()
    if not ws:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "No workspace for user"}},
        )
    return ws


async def require_workspace_role(
    workspace_id: uuid.UUID,
    user: User,
    session: AsyncSession,
    roles: Iterable[str],
) -> WorkspaceMember:
    """Проверяет, что у user есть нужная role в workspace."""
    res = await session.execute(
        select(WorkspaceMember)
        .where(WorkspaceMember.workspace_id == workspace_id)
        .where(WorkspaceMember.user_id == user.id)
    )
    m = res.scalar_one_or_none()
    if not m or m.role not in set(roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "forbidden", "message": "Insufficient workspace role"}},
        )
    return m
