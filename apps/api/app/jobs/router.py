"""Jobs endpoints."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from rq import Queue
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.db import get_session
from app.core.redis import get_sync_redis
from app.db.models import CrmConnection, Job, User, Workspace, WorkspaceMember

router = APIRouter(tags=["jobs"])


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def _progress_percent(result: Any) -> int | None:
    if not isinstance(result, dict):
        return None
    progress = result.get("progress")
    if not isinstance(progress, dict):
        return None
    value = progress.get("percent")
    try:
        if value is None:
            return None
        return min(100, max(0, int(value)))
    except (TypeError, ValueError):
        return None


def _export_estimate(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    estimate = payload.get("export_estimate")
    return estimate if isinstance(estimate, dict) else {}


def _queue_details(j: Job) -> dict[str, Any]:
    """Best-effort RQ queue position and ETA without exposing payload secrets."""
    queue_position: int | None = None
    jobs_ahead: int | None = None
    queue_length: int | None = None
    if j.status == "queued" and j.rq_job_id:
        try:
            queue = Queue(j.queue, connection=get_sync_redis())
            job_ids = list(queue.job_ids)
            queue_length = len(job_ids)
            if j.rq_job_id in job_ids:
                queue_position = job_ids.index(j.rq_job_id) + 1
                jobs_ahead = queue_position - 1
        except Exception:
            queue_position = None
            jobs_ahead = None
            queue_length = None

    estimate = _export_estimate(j.payload)
    duration_seconds = _safe_int(estimate.get("duration_seconds"))
    wait_seconds: int | None = None
    remaining_seconds: int | None = None

    if j.status == "queued":
        wait_seconds = (jobs_ahead or 0) * duration_seconds if duration_seconds else None
        remaining_seconds = (
            (wait_seconds or 0) + duration_seconds if duration_seconds else None
        )
    elif j.status == "running" and duration_seconds:
        percent = _progress_percent(j.result)
        if percent and percent > 0 and j.started_at:
            started = j.started_at
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            elapsed = max(
                0,
                int((datetime.now(timezone.utc) - started.astimezone(timezone.utc)).total_seconds()),
            )
            remaining_seconds = int(max(0, elapsed * ((100 - percent) / percent)))
        else:
            remaining_seconds = duration_seconds

    return {
        "queue_position": queue_position,
        "jobs_ahead": jobs_ahead,
        "queue_length": queue_length,
        "estimated_wait_seconds": wait_seconds,
        "estimated_duration_seconds": duration_seconds or None,
        "estimated_remaining_seconds": remaining_seconds,
        "estimated_records": _safe_int(estimate.get("records")) or None,
    }


def _serialize(j: Job) -> dict[str, Any]:
    return {
        "id": str(j.id),
        "kind": j.kind,
        "queue": j.queue,
        "status": j.status,
        "payload": j.payload or {},
        "result": j.result,
        "error": j.error,
        "rq_job_id": j.rq_job_id,
        "crm_connection_id": str(j.crm_connection_id) if j.crm_connection_id else None,
        "started_at": j.started_at.isoformat() if j.started_at else None,
        "finished_at": j.finished_at.isoformat() if j.finished_at else None,
        "created_at": j.created_at.isoformat() if j.created_at else None,
    } | _queue_details(j)


async def _user_has_ws_access(
    session: AsyncSession, user: User, workspace_id: uuid.UUID
) -> bool:
    m = (
        await session.execute(
            select(WorkspaceMember)
            .where(WorkspaceMember.workspace_id == workspace_id)
            .where(WorkspaceMember.user_id == user.id)
        )
    ).scalar_one_or_none()
    return m is not None


@router.get("/jobs/{job_id}")
async def get_job(
    job_id: uuid.UUID,
    user: User = Depends(get_current_user),
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
    if job.workspace_id and not await _user_has_ws_access(session, user, job.workspace_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "forbidden", "message": "No access to job"}},
        )
    return _serialize(job)


@router.get("/crm/connections/{connection_id}/jobs")
async def list_connection_jobs(
    connection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    # Проверим доступ к connection.
    conn = (
        await session.execute(select(CrmConnection).where(CrmConnection.id == connection_id))
    ).scalar_one_or_none()
    if not conn:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Connection not found"}},
        )
    if not await _user_has_ws_access(session, user, conn.workspace_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "forbidden", "message": "No access"}},
        )
    rows = (
        await session.execute(
            select(Job)
            .where(Job.crm_connection_id == connection_id)
            .order_by(Job.created_at.desc())
            .limit(100)
        )
    ).scalars().all()
    return [_serialize(j) for j in rows]
