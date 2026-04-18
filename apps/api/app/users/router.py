"""
Users router — совместимость для FE.

Основной endpoint `GET /auth/me` живёт в auth-роутере. Здесь — alias
`GET /users/me`, часто используемый фронтом, возвращающий тот же объект.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.schemas import MeResponse
from app.core.db import get_session
from app.db.models import User, Workspace, WorkspaceMember

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=MeResponse)
async def users_me(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MeResponse:
    """Alias для `GET /auth/me` (удобно для FE)."""
    rows = (
        await session.execute(
            select(WorkspaceMember, Workspace)
            .join(Workspace, Workspace.id == WorkspaceMember.workspace_id)
            .where(WorkspaceMember.user_id == user.id)
            .where(Workspace.status != "deleted")
        )
    ).all()
    workspaces = [
        {"id": str(ws.id), "name": ws.name, "role": m.role}
        for (m, ws) in rows
    ]
    return MeResponse(
        id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        locale=user.locale,
        email_verified=user.email_verified_at is not None,
        two_factor_enabled=user.two_factor_enabled,
        workspaces=workspaces,
    )
