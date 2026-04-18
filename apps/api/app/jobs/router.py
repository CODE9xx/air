"""Jobs endpoints."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.db import get_session
from app.db.models import CrmConnection, Job, User, Workspace, WorkspaceMember

router = APIRouter(tags=["jobs"])


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
    }


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
