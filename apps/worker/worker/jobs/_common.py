"""
Общие утилиты для job'ов: обновление public.jobs row (status, result, error).

Все jobs должны обновлять запись ``public.jobs`` по ``job_row_id`` (UUID из
payload). BE при enqueue создаёт эту row и кладёт id в payload.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from ..lib.db import sync_session


def _now() -> datetime:
    return datetime.now(timezone.utc)


def mark_job_running(job_row_id: str | None) -> None:
    """UPDATE jobs SET status='running', started_at=NOW()."""
    if not job_row_id:
        return
    with sync_session() as sess:
        sess.execute(
            text(
                "UPDATE jobs SET status='running', started_at=NOW() "
                "WHERE id = CAST(:rid AS UUID) AND status IN ('queued','running')"
            ),
            {"rid": job_row_id},
        )


def mark_job_succeeded(job_row_id: str | None, result: dict[str, Any] | None = None) -> None:
    if not job_row_id:
        return
    with sync_session() as sess:
        sess.execute(
            text(
                "UPDATE jobs SET status='succeeded', finished_at=NOW(), result = CAST(:res AS JSONB) "
                "WHERE id = CAST(:rid AS UUID)"
            ),
            {"rid": job_row_id, "res": _json(result or {})},
        )


def mark_job_failed(job_row_id: str | None, error: str) -> None:
    if not job_row_id:
        return
    with sync_session() as sess:
        sess.execute(
            text(
                "UPDATE jobs SET status='failed', finished_at=NOW(), error=:err "
                "WHERE id = CAST(:rid AS UUID)"
            ),
            {"rid": job_row_id, "err": error[:4000]},
        )


def new_uuid() -> str:
    return str(uuid.uuid4())


def short_id() -> str:
    """8 hex-символов из md5(uuid4()) — для tenant-schema."""
    return hashlib.md5(uuid.uuid4().hex.encode()).hexdigest()[:8]


def _json(obj: Any) -> str:
    import json

    return json.dumps(obj, ensure_ascii=False, default=str)
