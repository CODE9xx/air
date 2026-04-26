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
from datetime import datetime, time, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import (
    get_current_user,
    get_current_workspace,
    require_workspace_role,
)
from app.billing.tokens import (
    build_full_export_quote,
    get_or_create_token_account,
    reserve_tokens_for_export_job,
    token_account_snapshot,
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
from app.crm.single_connection import ensure_no_existing_crm_connection
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
_TOKEN_ESTIMATE_DEFAULT_AVG = {
    "deals": 1875,
    "contacts": 274,
    "companies": 402,
    "lead_notes": 159,
    "events": 182,
}
_TOKEN_ESTIMATE_LABELS = {
    "deals": "Сделки",
    "contacts": "Контакты",
    "companies": "Компании",
    "lead_notes": "Письма и notes",
    "events": "Events",
}
_CALL_TOKENS_PER_MINUTE_LOW = 350
_CALL_TOKENS_PER_MINUTE_HIGH = 570
_SYNC_CADENCE_SECONDS = {
    "manual": 24 * 60 * 60,
    "free": 24 * 60 * 60,
    "start": 24 * 60 * 60,
    "team": 60 * 60,
    "pro": 15 * 60,
    "enterprise": 15 * 60,
}
_FULL_EXPORT_MIN_DURATION_SECONDS = 5 * 60
_FULL_EXPORT_MAX_DURATION_SECONDS = 6 * 60 * 60


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _connection_incremental_since_iso(conn: CrmConnection) -> str | None:
    """Prefer successful real pull timestamp; fallback to legacy last_sync_at."""
    metadata = conn.metadata_json or {}
    last_pull_at = metadata.get("last_pull_at")
    if isinstance(last_pull_at, str) and last_pull_at.strip():
        return last_pull_at.strip()
    if conn.last_sync_at:
        dt = conn.last_sync_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    return None


def _parse_sync_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str) and value.strip():
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _sync_summary(c: CrmConnection, plan_key: str | None = None) -> dict[str, Any]:
    key = str(plan_key or "free").lower()
    cadence = _SYNC_CADENCE_SECONDS.get(key, _SYNC_CADENCE_SECONDS["free"])
    metadata = c.metadata_json or {}
    last_pull = _parse_sync_datetime(metadata.get("last_pull_at")) or _parse_sync_datetime(
        c.last_sync_at
    )
    return {
        "mode": "incremental",
        "plan_key": key,
        "cadence_seconds": cadence,
        "last_auto_sync_at": metadata.get("last_auto_sync_at"),
        "next_auto_sync_at": (
            (last_pull + timedelta(seconds=cadence)).isoformat() if last_pull else None
        ),
    }


async def _active_pull_job_count(
    session: AsyncSession,
    *,
    connection_id: uuid.UUID,
) -> int:
    value = (
        await session.execute(
            text(
                "SELECT COUNT(*) FROM jobs "
                "WHERE crm_connection_id = CAST(:connection_id AS UUID) "
                "  AND kind = 'pull_amocrm_core' "
                "  AND status IN ('queued', 'running')"
            ),
            {"connection_id": str(connection_id)},
        )
    ).scalar_one()
    return int(value or 0)


def _serialize_conn(c: CrmConnection, *, plan_key: str | None = None) -> dict[str, Any]:
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
        "sync": _sync_summary(c, plan_key=plan_key),
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


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def _build_token_estimate(
    *,
    connection_id: str,
    period: str = "all_time",
    metadata: dict[str, Any],
    call_minutes: int | None = None,
) -> dict[str, Any]:
    snapshot = metadata.get("token_estimate_snapshot")
    normalized_period = period if period in {"all_time", "active_export"} else "all_time"
    counts_source: dict[str, Any] = {}
    avg_source: dict[str, Any] = {}
    confidence: dict[str, str] = {}
    basis = "active_export_lower_bound"
    source = "active_export_counts"
    captured_at = None
    date_from = None
    date_to = None
    notes: list[str] = []

    if isinstance(snapshot, dict) and isinstance(snapshot.get("counts"), dict):
        counts_source = snapshot.get("counts") or {}
        avg_source = snapshot.get("avg_tokens") or {}
        confidence = snapshot.get("confidence") or {}
        basis = "full_database_snapshot"
        source = str(snapshot.get("source") or "metadata_snapshot")
        captured_at = snapshot.get("captured_at")
        if isinstance(snapshot.get("notes"), list):
            notes = [str(item) for item in snapshot["notes"]]
        active = metadata.get("active_export")
        if normalized_period == "active_export" and isinstance(active, dict):
            active_counts = active.get("counts") if isinstance(active.get("counts"), dict) else {}
            snapshot_deals = _safe_int(counts_source.get("deals"))
            active_deals = _safe_int(active_counts.get("deals"))
            if snapshot_deals > 0 and active_deals > 0:
                ratio = active_deals / snapshot_deals
                counts_source = {
                    key: int(round(_safe_int(counts_source.get(key)) * ratio))
                    for key in ("deals", "contacts", "companies", "lead_notes", "events")
                }
                counts_source["deals"] = active_deals
                basis = "active_export_scaled"
                source = "active_export_scaled_from_snapshot"
                captured_at = active.get("completed_at") or captured_at
                date_from = active.get("date_from")
                date_to = active.get("date_to")
                notes.append(
                    "Active export period estimate is scaled from full snapshot by deal-count ratio."
                )
    else:
        active = metadata.get("active_export")
        if isinstance(active, dict) and isinstance(active.get("counts"), dict):
            counts_source = active.get("counts") or {}
            captured_at = active.get("completed_at")
            date_from = active.get("date_from")
            date_to = active.get("date_to")
        elif isinstance(metadata.get("last_pull_counts"), dict):
            counts_source = metadata.get("last_pull_counts") or {}
        elif isinstance(metadata.get("last_trial_export_counts"), dict):
            counts_source = metadata.get("last_trial_export_counts") or {}
            source = "trial_export_counts"
        notes.append(
            "Full amoCRM census is not stored yet; estimate is a lower bound from cached export counts."
        )

    items: list[dict[str, Any]] = []
    total_without_calls = 0
    for key in ("deals", "contacts", "companies", "lead_notes", "events"):
        count = _safe_int(counts_source.get(key))
        avg_tokens = _safe_int(
            avg_source.get(key),
            _TOKEN_ESTIMATE_DEFAULT_AVG[key],
        )
        estimated_tokens = count * avg_tokens
        total_without_calls += estimated_tokens
        items.append(
            {
                "key": key,
                "label": _TOKEN_ESTIMATE_LABELS[key],
                "count": count,
                "avg_tokens": avg_tokens,
                "estimated_tokens": estimated_tokens,
                "confidence": confidence.get(key, "estimate"),
            }
        )

    normalized_call_minutes = _safe_int(call_minutes)
    calls_low = normalized_call_minutes * _CALL_TOKENS_PER_MINUTE_LOW
    calls_high = normalized_call_minutes * _CALL_TOKENS_PER_MINUTE_HIGH
    return {
        "connection_id": connection_id,
        "period": normalized_period,
        "source": source,
        "basis": basis,
        "date_from": date_from,
        "date_to": date_to,
        "captured_at": captured_at,
        "encoding": "o200k_base",
        "items": items,
        "total_tokens_without_calls": total_without_calls,
        "calls": {
            "minutes": normalized_call_minutes,
            "tokens_per_minute_low": _CALL_TOKENS_PER_MINUTE_LOW,
            "tokens_per_minute_high": _CALL_TOKENS_PER_MINUTE_HIGH,
            "estimated_tokens_low": calls_low,
            "estimated_tokens_high": calls_high,
            "confidence": "scenario",
        },
        "total_tokens_low": total_without_calls + calls_low,
        "total_tokens_high": total_without_calls + calls_high,
        "notes": notes,
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
    await ensure_no_existing_crm_connection(session, ws.id)

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
    plan_key = (
        await session.execute(
            text(
                "SELECT plan_key FROM token_accounts "
                "WHERE workspace_id = CAST(:workspace_id AS UUID)"
            ),
            {"workspace_id": str(conn.workspace_id)},
        )
    ).scalar_one_or_none()
    return _serialize_conn(conn, plan_key=plan_key)


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


@router.get("/connections/{connection_id}/token-estimate")
async def token_estimate(
    connection_id: uuid.UUID,
    period: str = "all_time",
    call_minutes: int | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    conn, _ = await _get_conn_for_user(session, user, connection_id)
    return _build_token_estimate(
        connection_id=str(conn.id),
        period=period,
        metadata=conn.metadata_json or {},
        call_minutes=call_minutes,
    )


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


def _export_date_start(value) -> datetime:
    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def _export_date_end(value) -> datetime:
    return datetime.combine(value, time.max, tzinfo=timezone.utc)


async def _cached_export_deals_count(
    session: AsyncSession,
    conn: CrmConnection,
    body: FullExportRequest,
) -> int | None:
    """Best-effort cached deal count from tenant data for quote scaling."""
    schema = conn.tenant_schema
    if not schema or not _TENANT_SCHEMA_RE.fullmatch(schema):
        return None
    clauses = [
        "d.created_at_external >= :created_from",
        "d.created_at_external <= :created_to",
    ]
    params: dict[str, Any] = {
        "created_from": _export_date_start(body.date_from),
        "created_to": _export_date_end(body.date_to),
    }
    selected = [str(pid).strip() for pid in body.pipeline_ids if str(pid).strip()]
    if selected:
        placeholders: list[str] = []
        for idx, pipeline_id in enumerate(selected):
            key = f"pipeline_{idx}"
            placeholders.append(f":{key}")
            params[key] = pipeline_id
        clauses.append(f"p.external_id IN ({', '.join(placeholders)})")

    q_schema = f'"{schema}"'
    try:
        value = (
            await session.execute(
                text(
                    f"SELECT COUNT(*) "
                    f"FROM {q_schema}.deals d "
                    f"LEFT JOIN {q_schema}.pipelines p ON p.id = d.pipeline_id "
                    f"WHERE {' AND '.join(clauses)}"
                ),
                params,
            )
        ).scalar()
    except Exception:
        return None
    return int(value or 0)


async def _build_full_export_quote_response(
    *,
    session: AsyncSession,
    conn: CrmConnection,
    ws: Workspace,
    body: FullExportRequest,
) -> dict[str, Any]:
    account = await get_or_create_token_account(session, ws)
    account_state = token_account_snapshot(account)
    cached_deals_count = await _cached_export_deals_count(session, conn, body)
    quote = build_full_export_quote(
        connection_id=str(conn.id),
        date_from=body.date_from,
        date_to=body.date_to,
        pipeline_ids=[str(pid) for pid in body.pipeline_ids],
        metadata=conn.metadata_json or {},
        available_mtokens=account_state["available_mtokens"],
        cached_deals_count=cached_deals_count,
    )
    estimated_deals = _safe_int(quote.get("estimated_deals"))
    estimated_contacts = _safe_int(quote.get("estimated_contacts"))
    snapshot = (conn.metadata_json or {}).get("token_estimate_snapshot")
    snapshot_counts = snapshot.get("counts") if isinstance(snapshot, dict) else {}
    estimated_companies = _safe_int(
        snapshot_counts.get("companies") if isinstance(snapshot_counts, dict) else 0
    )
    estimated_records = max(0, estimated_deals + estimated_contacts + estimated_companies)
    quote["estimated_records"] = estimated_records
    quote["estimated_duration_seconds"] = _estimate_export_duration_seconds(
        estimated_records
    )
    quote["token_account"] = account_state
    return quote


def _estimate_export_duration_seconds(estimated_records: int) -> int:
    """Conservative UI ETA for amoCRM API + DB upserts.

    This is not a billing value. It only gives the client an understandable
    range before the worker has real progress. Current worker updates progress
    by stages, so the running ETA becomes more accurate after the first steps.
    """
    if estimated_records <= 0:
        return 30 * 60
    # Around 20 imported rows/second including API latency, JSON processing,
    # upserts, and DB round-trips. Bound it so the UI never promises impossible
    # precision for tiny or very large accounts.
    seconds = int(_FULL_EXPORT_MIN_DURATION_SECONDS + (estimated_records / 20))
    return min(_FULL_EXPORT_MAX_DURATION_SECONDS, max(_FULL_EXPORT_MIN_DURATION_SECONDS, seconds))


@router.post("/connections/{connection_id}/full-export/quote")
async def full_export_quote(
    connection_id: uuid.UUID,
    body: FullExportRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    conn, ws = await _get_conn_for_user(session, user, connection_id)
    if body.date_from > body.date_to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": "validation_error", "message": "date_from must be <= date_to"}},
        )
    return await _build_full_export_quote_response(
        session=session,
        conn=conn,
        ws=ws,
        body=body,
    )


@router.post("/connections/{connection_id}/full-export", status_code=status.HTTP_202_ACCEPTED)
async def full_export(
    connection_id: uuid.UUID,
    body: FullExportRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> JobCreatedResponse:
    conn, ws = await _get_conn_for_user(session, user, connection_id)
    if await _active_pull_job_count(session, connection_id=conn.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "sync_already_running",
                    "message": "amoCRM sync is already queued or running",
                }
            },
        )
    if body.date_from > body.date_to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": "validation_error", "message": "date_from must be <= date_to"}},
        )
    quote = await _build_full_export_quote_response(
        session=session,
        conn=conn,
        ws=ws,
        body=body,
    )
    if not quote["can_start"]:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": {
                    "code": "insufficient_tokens",
                    "message": "Недостаточно AIC9-токенов для выгрузки",
                    "quote": quote,
                }
            },
        )
    payload = {
        "connection_id": str(conn.id),
        "first_pull": False,
        "date_from_iso": body.date_from.isoformat(),
        "date_to_iso": body.date_to.isoformat(),
        "pipeline_ids": [str(pid) for pid in body.pipeline_ids],
        "cleanup_trial": True,
        "export_estimate": {
            "records": quote.get("estimated_records", 0),
            "duration_seconds": quote.get("estimated_duration_seconds", 0),
            "deals": quote.get("estimated_deals", 0),
            "contacts": quote.get("estimated_contacts", 0),
            "tokens": quote.get("estimated_tokens", 0),
        },
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
    reservation = await reserve_tokens_for_export_job(
        session,
        workspace=ws,
        crm_connection_id=conn.id,
        job=job,
        quote=quote,
    )
    rq_id = enqueue(
        "pull_amocrm_core", payload, job_row_id=str(job.id)
    )
    job.rq_job_id = rq_id
    await session.commit()
    return JobCreatedResponse(
        job_id=str(job.id),
        reservation_id=str(reservation.id),
        reserved_tokens=quote["estimated_tokens"],
    )


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
    if await _active_pull_job_count(session, connection_id=conn.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "sync_already_running",
                    "message": "amoCRM sync is already queued or running",
                }
            },
        )
    payload = {
        "connection_id": str(conn.id),
        "first_pull": False,
        "cleanup_trial": False,
    }
    since_iso = _connection_incremental_since_iso(conn)
    if since_iso:
        payload["since_iso"] = since_iso
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
    rq_id = enqueue("pull_amocrm_core", payload, job_row_id=str(job.id))
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
