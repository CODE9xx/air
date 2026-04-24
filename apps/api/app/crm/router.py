"""
CRM Connections router.

Path-стиль mixed:
  * workspace-scoped: `/workspaces/:wsid/crm/connections` (из CONTRACT.md);
  * convenience: `/crm/connections` и `/crm/connections/:id/*` — берут current ws.

В MOCK_CRM_MODE создаём подключение без внешних вызовов, статус=active,
tenant_schema=NULL (его создаёт bootstrap_tenant_schema job).
"""
from __future__ import annotations

import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import (
    get_current_user,
    get_current_workspace,
    require_workspace_role,
)
from app.core.db import get_session
from app.core.email import send_verification_code
from app.core.jobs import enqueue, queue_for_kind
from app.core.security import generate_email_code, hash_secret, verify_secret
from app.core.settings import get_settings
from app.crm.schemas import (
    CreateMockConnectionRequest,
    DeleteConfirmRequest,
    ExportEstimateRequest,
    FullExportRequest,
    JobCreatedResponse,
    PatchConnectionRequest,
)
from app.db.models import (
    CrmConnection,
    DeletionRequest,
    Job,
    User,
    Workspace,
    WorkspaceMember,
)

router = APIRouter(prefix="/crm", tags=["crm"])

# Workspace-scoped router (Task #52.4) — монтируется без prefix="/crm",
# чтобы путь был абсолютным `/workspaces/{workspace_id}/crm/connections`
# согласно CONTRACT.md. Фронт по-этому пути и ходит:
# см. apps/web/app/[locale]/app/connections/page.tsx — api.get(
# `/workspaces/${wsId}/crm/connections`). До #52.4 роут отсутствовал →
# FastAPI отдавал 404, connection не показывался после рефреша.
ws_crm_router = APIRouter(tags=["crm"])

settings = get_settings()
_TENANT_SCHEMA_RE = re.compile(r"^crm_amo_[0-9a-f]{8}$")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _serialize_conn(c: CrmConnection) -> dict[str, Any]:
    """Возвращаем безопасную выборку полей. НЕ включаем токены."""
    return {
        "id": str(c.id),
        "workspace_id": str(c.workspace_id),
        "name": c.name,
        "provider": c.provider,
        "status": c.status,
        "external_account_id": c.external_account_id,
        "external_domain": c.external_domain,
        "tenant_schema": c.tenant_schema,
        "last_sync_at": c.last_sync_at.isoformat() if c.last_sync_at else None,
        "token_expires_at": c.token_expires_at.isoformat() if c.token_expires_at else None,
        "last_error": c.last_error,
        "metadata": c.metadata_json or {},
        "created_at": c.created_at.isoformat() if c.created_at else None,
        # #44.6 — public-safe поля external_button.
        "amocrm_auth_mode": c.amocrm_auth_mode,
        "amocrm_external_integration_id": c.amocrm_external_integration_id,
        "amocrm_credentials_received_at": (
            c.amocrm_credentials_received_at.isoformat()
            if c.amocrm_credentials_received_at
            else None
        ),
    }


async def _get_conn_for_user(
    session: AsyncSession,
    user: User,
    connection_id: uuid.UUID,
) -> tuple[CrmConnection, Workspace]:
    """Находит connection + workspace и проверяет членство user."""
    row = (
        await session.execute(
            select(CrmConnection, Workspace)
            .join(Workspace, Workspace.id == CrmConnection.workspace_id)
            .where(CrmConnection.id == connection_id)
        )
    ).first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Connection not found"}},
        )
    conn, ws = row
    # Упрощённо — проверяем owner. (В V1 — через WorkspaceMember.)
    if ws.owner_user_id != user.id:
        # Пытаемся через members.
        from app.db.models import WorkspaceMember

        m = (
            await session.execute(
                select(WorkspaceMember)
                .where(WorkspaceMember.workspace_id == ws.id)
                .where(WorkspaceMember.user_id == user.id)
            )
        ).scalar_one_or_none()
        if not m:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": {"code": "forbidden", "message": "Not a workspace member"}},
            )
    return conn, ws


# -------------------- List + Create --------------------

@router.get("/connections")
async def list_connections(
    user: User = Depends(get_current_user),
    ws: Workspace = Depends(get_current_workspace),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(CrmConnection)
            .where(CrmConnection.workspace_id == ws.id)
            .where(CrmConnection.status != "deleted")
            .order_by(CrmConnection.created_at.desc())
        )
    ).scalars().all()
    return [_serialize_conn(c) for c in rows]


# -------------------- Workspace-scoped list (CONTRACT.md, #52.4) --------------------

@ws_crm_router.get("/workspaces/{workspace_id}/crm/connections")
async def list_workspace_connections(
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """
    Список CRM-подключений конкретного workspace (из CONTRACT.md).

    Отдельный от ``GET /crm/connections`` путь, потому что фронт-кабинет
    знает workspace_id из ``user.workspaces[0].id`` и бьёт сразу по
    workspace-scoped path — без полагания на серверный ``get_current_workspace``
    (который в будущем multi-workspace MVP станет неоднозначным).

    Выборка идентична ``GET /crm/connections`` (owner или member ws,
    все status != 'deleted' — active/pending/paused/failed включены;
    external_button НЕ фильтруется). Возвращает 404 если workspace нет или
    помечен deleted; 403 если юзер не owner и не в members.
    """
    ws = await session.get(Workspace, workspace_id)
    if ws is None or ws.status == "deleted":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Workspace not found"}},
        )
    if ws.owner_user_id != user.id:
        member = (
            await session.execute(
                select(WorkspaceMember)
                .where(WorkspaceMember.workspace_id == ws.id)
                .where(WorkspaceMember.user_id == user.id)
            )
        ).scalar_one_or_none()
        if member is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": {
                        "code": "forbidden",
                        "message": "Not a workspace member",
                    }
                },
            )
    rows = (
        await session.execute(
            select(CrmConnection)
            .where(CrmConnection.workspace_id == ws.id)
            .where(CrmConnection.status != "deleted")
            .order_by(CrmConnection.created_at.desc())
        )
    ).scalars().all()
    return [_serialize_conn(c) for c in rows]


@router.post("/connections/mock-amocrm", status_code=status.HTTP_201_CREATED)
async def create_mock_amocrm(
    body: CreateMockConnectionRequest,
    user: User = Depends(get_current_user),
    ws: Workspace = Depends(get_current_workspace),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    # Лимит ≤10 amocrm на workspace (исключая deleted).
    count_row = await session.execute(
        select(func.count(CrmConnection.id))
        .where(CrmConnection.workspace_id == ws.id)
        .where(CrmConnection.provider == "amocrm")
        .where(CrmConnection.status != "deleted")
    )
    count = count_row.scalar() or 0
    if count >= 10:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "conflict", "message": "amoCRM connections limit reached (10)"}},
        )

    shortid = secrets.token_hex(4)
    conn = CrmConnection(
        workspace_id=ws.id,
        name=body.name,
        provider="amocrm",
        status="active",
        external_account_id=f"mock-{shortid}",
        external_domain="mock-amo.local",
        tenant_schema=None,
        metadata_json={"mock": True},
    )
    session.add(conn)
    await session.flush()

    # Task #52.6: create public.jobs row FIRST (to get job.id), THEN enqueue
    # with job_row_id in worker kwargs, THEN set rq_job_id, THEN commit.
    # Без этого worker получает job_row_id=None → mark_job_* no-op'ит →
    # status навсегда залипает в "queued".
    payload = {"connection_id": str(conn.id)}
    job = Job(
        workspace_id=ws.id,
        crm_connection_id=conn.id,
        kind="bootstrap_tenant_schema",
        queue=queue_for_kind("bootstrap_tenant_schema"),
        status="queued",
        payload=payload,
    )
    session.add(job)
    await session.flush()  # populates job.id from server_default gen_random_uuid()
    rq_id = enqueue(
        "bootstrap_tenant_schema", payload, job_row_id=str(job.id)
    )
    job.rq_job_id = rq_id

    await session.commit()
    return _serialize_conn(conn)


# -------------------- GET/PATCH single --------------------

@router.get("/connections/{connection_id}")
async def get_connection(
    connection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    conn, _ = await _get_conn_for_user(session, user, connection_id)
    return _serialize_conn(conn)


@router.patch("/connections/{connection_id}")
async def patch_connection(
    connection_id: uuid.UUID,
    body: PatchConnectionRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    conn, _ = await _get_conn_for_user(session, user, connection_id)
    if body.name is not None:
        conn.name = body.name
    await session.commit()
    return _serialize_conn(conn)


# -------------------- Pause/Resume --------------------

@router.post("/connections/{connection_id}/pause")
async def pause_connection(
    connection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    conn, _ = await _get_conn_for_user(session, user, connection_id)
    if conn.status in {"deleted", "deleting"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "conflict", "message": "Connection cannot be paused"}},
        )
    conn.status = "paused"
    await session.commit()
    return _serialize_conn(conn)


@router.post("/connections/{connection_id}/resume")
async def resume_connection(
    connection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    conn, _ = await _get_conn_for_user(session, user, connection_id)
    if conn.status != "paused":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "conflict", "message": "Connection is not paused"}},
        )
    conn.status = "active"
    await session.commit()
    return _serialize_conn(conn)


# -------------------- Delete flow --------------------

@router.post(
    "/connections/{connection_id}/delete/request",
    status_code=status.HTTP_202_ACCEPTED,
)
async def delete_request(
    connection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    conn, ws = await _get_conn_for_user(session, user, connection_id)
    if ws.owner_user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "forbidden", "message": "Only owner can delete"}},
        )
    if conn.status in {"deleted", "deleting"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "conflict", "message": "Already deleted"}},
        )
    # Не даём вторую активную заявку.
    active = (
        await session.execute(
            select(DeletionRequest)
            .where(DeletionRequest.crm_connection_id == conn.id)
            .where(DeletionRequest.status == "awaiting_code")
        )
    ).scalar_one_or_none()
    if active:
        return {
            "deletion_request_id": str(active.id),
            "expires_at": active.expires_at.isoformat(),
        }

    code = generate_email_code()
    expires_at = _now() + timedelta(minutes=10)
    req = DeletionRequest(
        crm_connection_id=conn.id,
        requested_by_user_id=user.id,
        email_code_hash=hash_secret(code),
        expires_at=expires_at,
        status="awaiting_code",
    )
    session.add(req)
    await session.commit()

    send_verification_code(user.email, code, "connection_delete")
    return {
        "deletion_request_id": str(req.id),
        "expires_at": expires_at.isoformat(),
    }


@router.post(
    "/connections/{connection_id}/delete/confirm",
    status_code=status.HTTP_202_ACCEPTED,
)
async def delete_confirm(
    connection_id: uuid.UUID,
    body: DeleteConfirmRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    conn, ws = await _get_conn_for_user(session, user, connection_id)
    if ws.owner_user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "forbidden", "message": "Only owner can delete"}},
        )

    req = (
        await session.execute(
            select(DeletionRequest)
            .where(DeletionRequest.crm_connection_id == conn.id)
            .where(DeletionRequest.status == "awaiting_code")
            .order_by(DeletionRequest.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if not req:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "No active deletion request"}},
        )
    if req.expires_at < _now():
        req.status = "expired"
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "code_expired", "message": "Code expired"}},
        )
    req.attempts += 1
    if req.attempts > req.max_attempts:
        req.status = "cancelled"
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"error": {"code": "too_many_attempts", "message": "Too many attempts"}},
        )
    if not verify_secret(req.email_code_hash, body.code):
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "validation_error", "message": "Invalid code"}},
        )

    req.status = "confirmed"
    req.confirmed_at = _now()
    conn.status = "deleting"

    # Task #52.6: create row first → enqueue with job_row_id → set rq_id.
    # Note: payload в public.jobs не содержит deletion_request_id
    # (исходное поведение), а worker kwargs — содержит через enqueue-payload.
    db_payload = {"connection_id": str(conn.id)}
    worker_payload = {
        "connection_id": str(conn.id),
        "deletion_request_id": str(req.id),
    }
    job = Job(
        workspace_id=ws.id,
        crm_connection_id=conn.id,
        kind="delete_connection_data",
        queue=queue_for_kind("delete_connection_data"),
        status="queued",
        payload=db_payload,
    )
    session.add(job)
    await session.flush()
    rq_id = enqueue(
        "delete_connection_data", worker_payload, job_row_id=str(job.id)
    )
    job.rq_job_id = rq_id
    await session.commit()

    return {"job_id": str(job.id)}


# -------------------- Audit --------------------

@router.post("/connections/{connection_id}/audit", status_code=status.HTTP_202_ACCEPTED)
async def audit_run(
    connection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> JobCreatedResponse:
    conn, ws = await _get_conn_for_user(session, user, connection_id)
    if conn.status in {"deleted", "deleting"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "conflict", "message": "Connection inactive"}},
        )
    # Task #52.6: row-first → enqueue with job_row_id.
    payload = {"connection_id": str(conn.id)}
    job = Job(
        workspace_id=ws.id,
        crm_connection_id=conn.id,
        kind="run_audit_report",
        queue=queue_for_kind("run_audit_report"),
        status="queued",
        payload=payload,
    )
    session.add(job)
    await session.flush()
    rq_id = enqueue("run_audit_report", payload, job_row_id=str(job.id))
    job.rq_job_id = rq_id
    await session.commit()
    return JobCreatedResponse(job_id=str(job.id))


@router.get("/connections/{connection_id}/audit/latest")
async def audit_latest(
    connection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    conn, _ = await _get_conn_for_user(session, user, connection_id)
    job = (
        await session.execute(
            select(Job)
            .where(Job.crm_connection_id == conn.id)
            .where(Job.kind == "run_audit_report")
            .order_by(Job.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if not job:
        return {"status": "none", "result": None}
    # В mock: если result ещё пуст — вернём placeholder.
    result = job.result
    if not result and job.status == "queued":
        # В mock-режиме выдаём иллюзию быстрого audit'а.
        result = {
            "mock": True,
            "deals_count": 0,
            "contacts_count": 0,
            "quality_score": None,
        }
    return {
        "job_id": str(job.id),
        "status": job.status,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "result": result,
    }


# -------------------- Trial export --------------------

@router.post("/connections/{connection_id}/trial-export", status_code=status.HTTP_202_ACCEPTED)
async def trial_export(
    connection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> JobCreatedResponse:
    conn, ws = await _get_conn_for_user(session, user, connection_id)
    payload = {"connection_id": str(conn.id), "trial": True}
    job = Job(
        workspace_id=ws.id,
        crm_connection_id=conn.id,
        kind="build_export_zip",
        queue=queue_for_kind("build_export_zip"),
        status="queued",
        payload=payload,
    )
    session.add(job)
    await session.flush()  # populates job.id (Task #52.6)
    rq_id = enqueue(
        "build_export_zip", payload, job_row_id=str(job.id)
    )
    job.rq_job_id = rq_id
    await session.commit()
    return JobCreatedResponse(job_id=str(job.id))


# -------------------- Export options + full export --------------------

@router.get("/connections/{connection_id}/export/options")
async def export_options(
    connection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    conn, _ = await _get_conn_for_user(session, user, connection_id)
    schema = conn.tenant_schema
    if not schema or not _TENANT_SCHEMA_RE.match(schema):
        return {
            "connection_id": str(conn.id),
            "pipelines": [],
            "source": "tenant_cache",
            "empty_reason": "tenant_schema_missing",
        }

    q_schema = f'"{schema}"'
    rows = (
        await session.execute(
            text(
                f"SELECT p.external_id, p.name, s.external_id, s.name, s.sort_order "
                f"FROM {q_schema}.pipelines p "
                f"LEFT JOIN {q_schema}.stages s ON s.pipeline_id = p.id "
                "WHERE p.external_id NOT LIKE 'ext-pipe-%' "
                "GROUP BY p.id, p.external_id, p.name, s.id, s.external_id, s.name, s.sort_order "
                "ORDER BY p.name, s.sort_order NULLS LAST, s.name"
            )
        )
    ).all()

    pipelines: dict[str, dict[str, Any]] = {}
    for row in rows:
        pipeline_id = str(row[0])
        item = pipelines.setdefault(
            pipeline_id,
            {"id": pipeline_id, "name": row[1] or pipeline_id, "stages": []},
        )
        if row[2] is not None:
            item["stages"].append(
                {"id": str(row[2]), "name": row[3] or str(row[2]), "sort_order": row[4]}
            )
    return {
        "connection_id": str(conn.id),
        "pipelines": list(pipelines.values()),
        "source": "tenant_cache",
        "empty_reason": None if pipelines else "no_real_pipelines_cached",
    }


# -------------------- Export estimate + full export --------------------

@router.post("/connections/{connection_id}/export/estimate")
async def export_estimate(
    connection_id: uuid.UUID,
    body: ExportEstimateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    conn, _ = await _get_conn_for_user(session, user, connection_id)
    days = max(1, (body.date_to - body.date_from).days)
    # Mock-оценка: 100 deals/день, 5 коп/deal.
    estimated_deals = days * 100
    estimated_cost_cents = estimated_deals * 5
    return {
        "connection_id": str(conn.id),
        "date_from": body.date_from.isoformat(),
        "date_to": body.date_to.isoformat(),
        "estimated_deals": estimated_deals,
        "estimated_cost_cents": estimated_cost_cents,
        "currency": "RUB",
        "mock": True,
    }


@router.post("/connections/{connection_id}/full-export", status_code=status.HTTP_202_ACCEPTED)
async def full_export(
    connection_id: uuid.UUID,
    body: FullExportRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> JobCreatedResponse:
    conn, ws = await _get_conn_for_user(session, user, connection_id)
    if body.date_from > body.date_to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": "validation_error", "message": "date_from must be <= date_to"}},
        )
    payload = {
        "connection_id": str(conn.id),
        "first_pull": False,
        "date_from_iso": body.date_from.isoformat(),
        "date_to_iso": body.date_to.isoformat(),
        "pipeline_ids": [str(pid) for pid in body.pipeline_ids],
        "cleanup_trial": True,
        "contacts_limit": 2000,
    }
    job = Job(
        workspace_id=ws.id,
        crm_connection_id=conn.id,
        kind="pull_amocrm_core",
        queue=queue_for_kind("pull_amocrm_core"),
        status="queued",
        payload=payload,
    )
    session.add(job)
    await session.flush()  # populates job.id (Task #52.6)
    rq_id = enqueue(
        "pull_amocrm_core", payload, job_row_id=str(job.id)
    )
    job.rq_job_id = rq_id
    await session.commit()
    return JobCreatedResponse(job_id=str(job.id))


# -------------------- Sync (convenience) --------------------

@router.post("/connections/{connection_id}/sync", status_code=status.HTTP_202_ACCEPTED)
async def sync_connection(
    connection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> JobCreatedResponse:
    conn, ws = await _get_conn_for_user(session, user, connection_id)
    if conn.status in {"deleted", "deleting", "lost_token"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "conflict", "message": "Cannot sync in current state"}},
        )
    payload = {"connection_id": str(conn.id)}
    job = Job(
        workspace_id=ws.id,
        crm_connection_id=conn.id,
        kind="fetch_crm_data",
        queue=queue_for_kind("fetch_crm_data"),
        status="queued",
        payload=payload,
    )
    session.add(job)
    await session.flush()  # populates job.id (Task #52.6)
    rq_id = enqueue("fetch_crm_data", payload, job_row_id=str(job.id))
    job.rq_job_id = rq_id
    await session.commit()
    return JobCreatedResponse(job_id=str(job.id))


# -------------------- Reconnect (mock: 501 если не mock) --------------------

@router.post("/connections/{connection_id}/reconnect")
async def reconnect(
    connection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    conn, _ = await _get_conn_for_user(session, user, connection_id)
    if not settings.mock_crm_mode:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail={"error": {"code": "mock_only", "message": "Real OAuth not available in MVP"}},
        )
    # В mock просто возвращаем "новую" ссылку.
    return {
        "oauth_authorize_url": f"{settings.base_url}/api/v1/crm/oauth/amocrm/start?connection_id={conn.id}",
        "mock": True,
    }
