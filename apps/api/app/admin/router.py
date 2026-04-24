"""
Admin router (`/admin`).

Все мутации пишут в `admin_audit_logs` в той же транзакции (ADR-008).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_admin, require_admin_role
from app.core.db import get_session
from app.core.jobs import enqueue, queue_for_kind
from app.core.rate_limit import client_ip, rate_limit
from app.core.security import create_access_token, hash_secret, verify_secret
from app.core.settings import get_settings
from app.db.models import (
    AdminAuditLog,
    AdminSession,
    AdminSupportSession,
    AdminUser,
    BillingAccount,
    BillingLedger,
    CrmConnection,
    Job,
    User,
    Workspace,
    WorkspaceMember,
)

router = APIRouter(prefix="/admin", tags=["admin"])
settings = get_settings()


def _now() -> datetime:
    return datetime.now(timezone.utc)


# -------------------- Schemas --------------------

class AdminLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class BillingAdjustRequest(BaseModel):
    amount_cents: int
    reason: str = Field(min_length=1, max_length=500)


class SupportModeStartRequest(BaseModel):
    workspace_id: uuid.UUID | None = None
    connection_id: uuid.UUID | None = None
    reason: str = Field(min_length=1, max_length=500)


# -------------------- Auth --------------------

@router.post(
    "/auth/login",
    dependencies=[Depends(rate_limit("admin_login_ip", limit=5, window_seconds=60, key_builder=client_ip))],
)
async def admin_login(
    body: AdminLoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    admin = (
        await session.execute(select(AdminUser).where(AdminUser.email == body.email))
    ).scalar_one_or_none()
    if not admin or not verify_secret(admin.password_hash, body.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "invalid_credentials", "message": "Bad credentials"}},
        )
    if admin.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "forbidden", "message": "Admin locked"}},
        )

    admin.last_login_at = _now()
    # Audit log.
    session.add(
        AdminAuditLog(
            admin_user_id=admin.id,
            action="admin_login",
            ip=client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    )
    await session.commit()

    access, ttl = create_access_token(str(admin.id), scope="admin")
    return {
        "access_token": access,
        "access_token_expires_in": ttl,
        "admin": {
            "id": str(admin.id),
            "email": admin.email,
            "role": admin.role,
        },
    }


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def admin_logout(
    admin: AdminUser = Depends(get_current_admin),
) -> Response:
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# -------------------- Workspaces --------------------

@router.get("/workspaces")
async def admin_workspaces(
    q: str | None = None,
    status_filter: str | None = None,
    page: int = 1,
    page_size: int = 50,
    admin: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    stmt = select(Workspace)
    if q:
        stmt = stmt.where(Workspace.name.ilike(f"%{q}%"))
    if status_filter:
        stmt = stmt.where(Workspace.status == status_filter)
    stmt = stmt.order_by(desc(Workspace.created_at)).limit(page_size).offset((page - 1) * page_size)
    rows = (await session.execute(stmt)).scalars().all()
    return {
        "workspaces": [
            {
                "id": str(ws.id),
                "name": ws.name,
                "slug": ws.slug,
                "status": ws.status,
                "created_at": ws.created_at.isoformat() if ws.created_at else None,
            }
            for ws in rows
        ],
        "page": page,
        "page_size": page_size,
    }


@router.get("/workspaces/{workspace_id}")
async def admin_workspace_detail(
    workspace_id: uuid.UUID,
    admin: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    ws = (
        await session.execute(select(Workspace).where(Workspace.id == workspace_id))
    ).scalar_one_or_none()
    if not ws:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Workspace not found"}},
        )
    conns = (
        await session.execute(
            select(CrmConnection).where(CrmConnection.workspace_id == workspace_id)
        )
    ).scalars().all()
    ba = (
        await session.execute(
            select(BillingAccount).where(BillingAccount.workspace_id == workspace_id)
        )
    ).scalar_one_or_none()
    return {
        "id": str(ws.id),
        "name": ws.name,
        "status": ws.status,
        "connections": [
            {"id": str(c.id), "provider": c.provider, "status": c.status, "name": c.name}
            for c in conns
        ],
        "billing": {
            "balance_cents": ba.balance_cents if ba else 0,
            "currency": ba.currency if ba else "RUB",
            "plan": ba.plan if ba else "free",
        },
    }


@router.post("/workspaces/{workspace_id}/pause")
async def admin_workspace_pause(
    workspace_id: uuid.UUID,
    request: Request,
    admin: AdminUser = Depends(require_admin_role("superadmin", "support")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    ws = (
        await session.execute(select(Workspace).where(Workspace.id == workspace_id))
    ).scalar_one_or_none()
    if not ws:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Workspace not found"}},
        )
    ws.status = "paused"
    session.add(
        AdminAuditLog(
            admin_user_id=admin.id,
            action="workspace_pause",
            target_type="workspace",
            target_id=workspace_id,
            ip=client_ip(request),
        )
    )
    await session.commit()
    return {"ok": True, "status": ws.status}


@router.post("/workspaces/{workspace_id}/resume")
async def admin_workspace_resume(
    workspace_id: uuid.UUID,
    request: Request,
    admin: AdminUser = Depends(require_admin_role("superadmin", "support")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    ws = (
        await session.execute(select(Workspace).where(Workspace.id == workspace_id))
    ).scalar_one_or_none()
    if not ws:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Workspace not found"}},
        )
    ws.status = "active"
    session.add(
        AdminAuditLog(
            admin_user_id=admin.id,
            action="workspace_resume",
            target_type="workspace",
            target_id=workspace_id,
            ip=client_ip(request),
        )
    )
    await session.commit()
    return {"ok": True, "status": ws.status}


# -------------------- Users --------------------

@router.get("/users")
async def admin_users(
    q: str | None = None,
    page: int = 1,
    page_size: int = 50,
    admin: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    stmt = select(User)
    if q:
        stmt = stmt.where(User.email.ilike(f"%{q}%"))
    stmt = stmt.order_by(desc(User.created_at)).limit(page_size).offset((page - 1) * page_size)
    rows = (await session.execute(stmt)).scalars().all()
    return {
        "users": [
            {
                "id": str(u.id),
                "email": u.email,
                "status": u.status,
                "email_verified": u.email_verified_at is not None,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in rows
        ],
        "page": page,
        "page_size": page_size,
    }


# -------------------- Connections --------------------

@router.get("/connections")
async def admin_connections(
    status_filter: str | None = None,
    page: int = 1,
    page_size: int = 50,
    admin: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    stmt = select(CrmConnection)
    if status_filter:
        stmt = stmt.where(CrmConnection.status == status_filter)
    stmt = stmt.order_by(desc(CrmConnection.created_at)).limit(page_size).offset((page - 1) * page_size)
    rows = (await session.execute(stmt)).scalars().all()
    return {
        "connections": [
            {
                "id": str(c.id),
                "workspace_id": str(c.workspace_id),
                "provider": c.provider,
                "status": c.status,
                "name": c.name,
                "external_account_id": c.external_account_id,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in rows
        ],
        "page": page,
        "page_size": page_size,
    }


@router.get("/connections/{connection_id}")
async def admin_connection_detail(
    connection_id: uuid.UUID,
    admin: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    c = (
        await session.execute(select(CrmConnection).where(CrmConnection.id == connection_id))
    ).scalar_one_or_none()
    if not c:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Connection not found"}},
        )
    return {
        "id": str(c.id),
        "workspace_id": str(c.workspace_id),
        "provider": c.provider,
        "status": c.status,
        "name": c.name,
        "external_account_id": c.external_account_id,
        "external_domain": c.external_domain,
        "tenant_schema": c.tenant_schema,
        "last_error": c.last_error,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


@router.post("/connections/{connection_id}/pause")
async def admin_connection_pause(
    connection_id: uuid.UUID,
    request: Request,
    admin: AdminUser = Depends(require_admin_role("superadmin", "support")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    c = (
        await session.execute(select(CrmConnection).where(CrmConnection.id == connection_id))
    ).scalar_one_or_none()
    if not c:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Connection not found"}},
        )
    c.status = "paused"
    session.add(
        AdminAuditLog(
            admin_user_id=admin.id,
            action="connection_pause",
            target_type="connection",
            target_id=connection_id,
            ip=client_ip(request),
        )
    )
    await session.commit()
    return {"ok": True}


@router.post("/connections/{connection_id}/resume")
async def admin_connection_resume(
    connection_id: uuid.UUID,
    request: Request,
    admin: AdminUser = Depends(require_admin_role("superadmin", "support")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    c = (
        await session.execute(select(CrmConnection).where(CrmConnection.id == connection_id))
    ).scalar_one_or_none()
    if not c:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Connection not found"}},
        )
    c.status = "active"
    session.add(
        AdminAuditLog(
            admin_user_id=admin.id,
            action="connection_resume",
            target_type="connection",
            target_id=connection_id,
            ip=client_ip(request),
        )
    )
    await session.commit()
    return {"ok": True}


# -------------------- Jobs --------------------

@router.get("/jobs")
async def admin_jobs(
    status_filter: str | None = None,
    page: int = 1,
    page_size: int = 50,
    admin: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    stmt = select(Job)
    if status_filter:
        stmt = stmt.where(Job.status == status_filter)
    stmt = stmt.order_by(desc(Job.created_at)).limit(page_size).offset((page - 1) * page_size)
    rows = (await session.execute(stmt)).scalars().all()
    return {
        "jobs": [
            {
                "id": str(j.id),
                "kind": j.kind,
                "status": j.status,
                "created_at": j.created_at.isoformat() if j.created_at else None,
            }
            for j in rows
        ],
        "page": page,
        "page_size": page_size,
    }


@router.post("/jobs/{job_id}/restart")
async def admin_job_restart(
    job_id: uuid.UUID,
    request: Request,
    admin: AdminUser = Depends(require_admin_role("superadmin", "support")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    job = (
        await session.execute(select(Job).where(Job.id == job_id))
    ).scalar_one_or_none()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Job not found"}},
        )
    # Task #52.6: создаём новую Job row, flush для получения id,
    # потом enqueue с job_row_id — без этого worker.mark_job_* никогда
    # не обновит status restart'нутого job'а.
    payload = job.payload or {}
    new_job = Job(
        workspace_id=job.workspace_id,
        crm_connection_id=job.crm_connection_id,
        kind=job.kind,
        queue=queue_for_kind(job.kind),
        status="queued",
        payload=payload,
    )
    session.add(new_job)
    await session.flush()
    rq_id = enqueue(job.kind, payload, job_row_id=str(new_job.id))
    new_job.rq_job_id = rq_id
    session.add(
        AdminAuditLog(
            admin_user_id=admin.id,
            action="job_restart",
            target_type="job",
            target_id=job.id,
            metadata_json={"new_job_id": str(new_job.id)},
            ip=client_ip(request),
        )
    )
    await session.commit()
    return {"ok": True, "new_job_id": str(new_job.id)}


# -------------------- Audit logs --------------------

@router.get("/audit-logs")
async def admin_audit_logs(
    admin_user_id: uuid.UUID | None = None,
    action: str | None = None,
    page: int = 1,
    page_size: int = 100,
    admin: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    stmt = select(AdminAuditLog)
    if admin_user_id:
        stmt = stmt.where(AdminAuditLog.admin_user_id == admin_user_id)
    if action:
        stmt = stmt.where(AdminAuditLog.action == action)
    stmt = stmt.order_by(desc(AdminAuditLog.created_at)).limit(page_size).offset((page - 1) * page_size)
    rows = (await session.execute(stmt)).scalars().all()
    return {
        "logs": [
            {
                "id": str(r.id),
                "admin_user_id": str(r.admin_user_id),
                "action": r.action,
                "target_type": r.target_type,
                "target_id": str(r.target_id) if r.target_id else None,
                "metadata": r.metadata_json or {},
                "ip": str(r.ip) if r.ip else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    }


# -------------------- Billing adjust --------------------

@router.post("/billing/adjust")
async def admin_billing_adjust(
    body: BillingAdjustRequest,
    request: Request,
    workspace_id: uuid.UUID,
    admin: AdminUser = Depends(require_admin_role("superadmin", "support")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    ba = (
        await session.execute(
            select(BillingAccount).where(BillingAccount.workspace_id == workspace_id)
        )
    ).scalar_one_or_none()
    if not ba:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Billing account not found"}},
        )
    ba.balance_cents += body.amount_cents
    session.add(
        BillingLedger(
            billing_account_id=ba.id,
            workspace_id=workspace_id,
            amount_cents=body.amount_cents,
            currency=ba.currency,
            kind="adjustment",
            description=body.reason,
            reference=f"admin:{admin.id}",
        )
    )
    session.add(
        AdminAuditLog(
            admin_user_id=admin.id,
            action="billing_adjustment",
            target_type="workspace",
            target_id=workspace_id,
            metadata_json={"amount_cents": body.amount_cents, "reason": body.reason},
            ip=client_ip(request),
        )
    )
    await session.commit()
    return {"ok": True, "balance_cents": ba.balance_cents}


# -------------------- Support mode --------------------

@router.post("/support-mode/start")
async def support_mode_start(
    body: SupportModeStartRequest,
    request: Request,
    admin: AdminUser = Depends(require_admin_role("superadmin", "support")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    workspace_id = body.workspace_id
    connection_id = body.connection_id
    if not workspace_id and connection_id:
        # Берём workspace из connection.
        c = (
            await session.execute(select(CrmConnection).where(CrmConnection.id == connection_id))
        ).scalar_one_or_none()
        if not c:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": {"code": "not_found", "message": "Connection not found"}},
            )
        workspace_id = c.workspace_id
    if not workspace_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "validation_error", "message": "workspace_id or connection_id required"}},
        )

    expires_at = _now() + timedelta(minutes=60)
    sup = AdminSupportSession(
        admin_user_id=admin.id,
        workspace_id=workspace_id,
        connection_id=connection_id,
        reason=body.reason,
        expires_at=expires_at,
    )
    session.add(sup)
    await session.flush()
    session.add(
        AdminAuditLog(
            admin_user_id=admin.id,
            action="support_mode_start",
            target_type="workspace",
            target_id=workspace_id,
            metadata_json={"reason": body.reason, "session_id": str(sup.id)},
            ip=client_ip(request),
        )
    )
    await session.commit()
    return {"support_session_id": str(sup.id), "expires_at": expires_at.isoformat()}


@router.post("/support-mode/end", status_code=status.HTTP_204_NO_CONTENT)
async def support_mode_end(
    request: Request,
    admin: AdminUser = Depends(require_admin_role("superadmin", "support")),
    session: AsyncSession = Depends(get_session),
) -> Response:
    rows = (
        await session.execute(
            select(AdminSupportSession)
            .where(AdminSupportSession.admin_user_id == admin.id)
            .where(AdminSupportSession.ended_at.is_(None))
        )
    ).scalars().all()
    for s in rows:
        s.ended_at = _now()
        session.add(
            AdminAuditLog(
                admin_user_id=admin.id,
                action="support_mode_end",
                target_type="workspace",
                target_id=s.workspace_id,
                metadata_json={"session_id": str(s.id)},
                ip=client_ip(request),
            )
        )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/support-mode/current")
async def support_mode_current(
    admin: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Текущая активная support-сессия (без ended_at и expires_at > now)."""
    now = _now()
    row = (
        await session.execute(
            select(AdminSupportSession)
            .where(AdminSupportSession.admin_user_id == admin.id)
            .where(AdminSupportSession.ended_at.is_(None))
            .where(AdminSupportSession.expires_at > now)
            .order_by(desc(AdminSupportSession.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()
    if not row:
        return {"active": False}
    return {
        "active": True,
        "support_session_id": str(row.id),
        "workspace_id": str(row.workspace_id),
        "connection_id": str(row.connection_id) if row.connection_id else None,
        "reason": row.reason,
        "expires_at": row.expires_at.isoformat(),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


# -------------------- AI admin endpoints (research aggregates, model runs) --------------------

@router.get("/ai/research-patterns")
async def admin_research_patterns(
    admin: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """
    Анонимизированные агрегаты AI-паттернов (из ``ai_research_patterns``).
    Без привязки к workspace.
    """
    from app.db.models import AiResearchPattern

    rows = (
        await session.execute(
            select(AiResearchPattern)
            .order_by(desc(AiResearchPattern.created_at))
            .limit(200)
        )
    ).scalars().all()
    return {
        "patterns": [
            {
                "id": str(r.id),
                "industry": r.industry,
                "pattern_type": r.pattern_type,
                "channel": r.channel,
                "sample_size": r.sample_size,
                "confidence": float(r.confidence) if r.confidence is not None else None,
                "summary": r.summary,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    }


@router.get("/ai/model-runs")
async def admin_model_runs(
    page: int = 1,
    page_size: int = 50,
    admin: AdminUser = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Список запусков LLM (расход токенов и ошибки)."""
    from app.db.models import AiModelRun

    rows = (
        await session.execute(
            select(AiModelRun)
            .order_by(desc(AiModelRun.created_at))
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
    ).scalars().all()
    return {
        "runs": [
            {
                "id": str(r.id),
                "provider": r.provider,
                "model": r.model,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "latency_ms": r.latency_ms,
                "cost_cents": r.cost_cents,
                "status": r.status,
                "error": r.error,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
        "page": page,
        "page_size": page_size,
    }
