"""
Integrations OAuth endpoints — amoCRM (и скелет под kommo/bx24).

Префикс: `/integrations/amocrm/oauth/*`.

При `MOCK_CRM_MODE=true`:
  * `start` — создаёт mock-подключение и редиректит на `/app/connections/<id>`;
  * `callback` — mock всегда успешен.

При реальном режиме (V1):
  * `start` — строит `authorize_url` через `packages/crm_connectors.amocrm`
    и кладёт CSRF-state в Redis (TTL 10 min);
  * `callback` — **501** до реализации (см. docs/api/CONTRACT.md §CRM).
"""
from __future__ import annotations

import secrets
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.db import get_session
from app.core.jobs import enqueue, queue_for_kind
from app.core.redis import get_redis
from app.core.settings import get_settings
from app.db.models import CrmConnection, Job, User, Workspace, WorkspaceMember

router = APIRouter(prefix="/integrations/amocrm/oauth", tags=["integrations"])
settings = get_settings()


async def _ensure_member(
    session: AsyncSession, user: User, workspace_id: uuid.UUID
) -> Workspace:
    """Проверяет, что user — member workspace, иначе 403."""
    from sqlalchemy import select

    ws = (
        await session.execute(select(Workspace).where(Workspace.id == workspace_id))
    ).scalar_one_or_none()
    if not ws:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Workspace not found"}},
        )
    m = (
        await session.execute(
            select(WorkspaceMember)
            .where(WorkspaceMember.workspace_id == workspace_id)
            .where(WorkspaceMember.user_id == user.id)
        )
    ).scalar_one_or_none()
    if not m or m.role not in {"owner", "admin"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "forbidden", "message": "Not an owner/admin"}},
        )
    return ws


@router.get("/start")
async def oauth_start(
    workspace_id: uuid.UUID,
    connection_name: str | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Any:
    """
    Начало OAuth для amoCRM.

    MOCK: сразу создаёт подключение active + enqueue bootstrap_tenant_schema,
    возвращает redirect на UI.
    REAL (V1): возвращает JSON с `authorize_url` + state, state — в Redis.
    """
    ws = await _ensure_member(session, user, workspace_id)

    if settings.mock_crm_mode:
        shortid = secrets.token_hex(4)
        conn = CrmConnection(
            workspace_id=ws.id,
            name=connection_name or "amoCRM (mock)",
            provider="amocrm",
            status="active",
            external_account_id=f"mock-{shortid}",
            external_domain="mock-amo.local",
            tenant_schema=None,
            metadata_json={"mock": True, "source": "oauth_start"},
        )
        session.add(conn)
        await session.flush()

        rq_id = enqueue("bootstrap_tenant_schema", {"connection_id": str(conn.id)})
        session.add(
            Job(
                workspace_id=ws.id,
                crm_connection_id=conn.id,
                kind="bootstrap_tenant_schema",
                queue=queue_for_kind("bootstrap_tenant_schema"),
                status="queued",
                payload={"connection_id": str(conn.id)},
                rq_job_id=rq_id,
            )
        )
        await session.commit()

        # В реальном сценарии — 302, но тестовый клиент удобнее с JSON.
        return {
            "mock": True,
            "connection_id": str(conn.id),
            "redirect_url": f"/app/connections/{conn.id}",
        }

    # Real mode (V1): строим authorize URL и кладём state в Redis.
    try:
        from crm_connectors.amocrm import AmoCrmConnector  # type: ignore
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail={
                "error": {
                    "code": "mock_only",
                    "message": f"Real OAuth not configured: {exc}",
                }
            },
        )

    state = secrets.token_urlsafe(24)
    redis = get_redis()
    await redis.setex(
        f"oauth_state:amocrm:{state}",
        600,  # 10 min TTL
        str(ws.id),
    )
    connector = AmoCrmConnector()
    redirect_uri = f"{settings.base_url}/api/v1/integrations/amocrm/oauth/callback"
    try:
        authorize_url = connector.oauth_authorize_url(state=state, redirect_uri=redirect_uri)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail={"error": {"code": "mock_only", "message": str(exc)}},
        )
    return {"authorize_url": authorize_url, "state": state}


@router.get("/callback")
async def oauth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> Any:
    """
    OAuth callback. В MOCK — всегда успех (на деле start уже всё сделал).
    В real mode — 501 (V1).
    """
    if settings.mock_crm_mode:
        # MOCK: просто редиректим на app.
        return RedirectResponse(url="/app/connections?flash=mock_oauth_ok")

    if not code or not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "validation_error", "message": "Missing code/state"}},
        )

    # V1: проверка state в Redis + exchange_code. Пока возвращаем 501.
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={
            "error": {
                "code": "mock_only",
                "message": "Real amoCRM OAuth callback — V1 (not implemented in MVP).",
            }
        },
    )
