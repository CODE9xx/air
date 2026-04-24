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
                "UPDATE jobs SET status='succeeded', finished_at=NOW(), "
                "  result = COALESCE(result, '{}'::jsonb) || CAST(:res AS JSONB) "
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


def update_job_progress(
    job_row_id: str | None,
    *,
    stage: str,
    completed_steps: int,
    total_steps: int,
    counts: dict[str, Any] | None = None,
) -> None:
    """Merge public, non-secret progress details into jobs.result."""
    if not job_row_id:
        return
    safe_total = max(1, int(total_steps))
    safe_completed = min(max(0, int(completed_steps)), safe_total)
    progress = {
        "stage": stage,
        "completed_steps": safe_completed,
        "total_steps": safe_total,
        "percent": int(round((safe_completed / safe_total) * 100)),
        "counts": counts or {},
        "updated_at": _now().isoformat(),
    }
    try:
        with sync_session() as sess:
            sess.execute(
                text(
                    "UPDATE jobs SET result = COALESCE(result, '{}'::jsonb) "
                    "  || CAST(:patch AS JSONB) "
                    "WHERE id = CAST(:rid AS UUID)"
                ),
                {"rid": job_row_id, "patch": _json({"progress": progress})},
            )
    except Exception:
        return


def create_job_notification(
    job_row_id: str | None,
    *,
    kind: str,
    title: str,
    body: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Create a workspace notification for a job without exposing job payload secrets."""
    if not job_row_id:
        return
    try:
        with sync_session() as sess:
            row = sess.execute(
                text(
                    "SELECT workspace_id, crm_connection_id "
                    "FROM jobs WHERE id = CAST(:rid AS UUID)"
                ),
                {"rid": job_row_id},
            ).fetchone()
            if row is None or row[0] is None:
                return
            sess.execute(
                text(
                    "INSERT INTO notifications("
                    "  workspace_id, user_id, kind, title, body, metadata"
                    ") VALUES ("
                    "  :workspace_id, NULL, :kind, :title, :body, CAST(:metadata AS JSONB)"
                    ")"
                ),
                {
                    "workspace_id": row[0],
                    "kind": kind,
                    "title": title,
                    "body": body,
                    "metadata": _json(
                        {
                            "job_id": job_row_id,
                            "crm_connection_id": str(row[1]) if row[1] else None,
                            **(metadata or {}),
                        }
                    ),
                },
            )
    except Exception:
        return


def charge_token_reservation_for_job(
    job_row_id: str | None,
    result: dict[str, Any] | None = None,
) -> None:
    """Finalize reserved AIC9 tokens after a paid job succeeds.

    Idempotent: if there is no reserved row for this job, it no-ops. OAuth
    bootstrap/sync jobs do not have reservations.
    """
    if not job_row_id:
        return
    with sync_session() as sess:
        row = sess.execute(
            text(
                "SELECT id, token_account_id, workspace_id, crm_connection_id, "
                "       amount_mtokens, metadata "
                "FROM token_reservations "
                "WHERE job_id = CAST(:rid AS UUID) AND status = 'reserved' "
                "FOR UPDATE"
            ),
            {"rid": job_row_id},
        ).fetchone()
        if row is None:
            return
        reservation_id, account_id, workspace_id, crm_connection_id, amount, metadata = row
        account = sess.execute(
            text(
                "UPDATE token_accounts SET "
                "  balance_mtokens = balance_mtokens - :amount, "
                "  reserved_mtokens = reserved_mtokens - :amount, "
                "  updated_at = NOW() "
                "WHERE id = :account_id "
                "RETURNING balance_mtokens, reserved_mtokens"
            ),
            {"amount": int(amount), "account_id": account_id},
        ).fetchone()
        if account is None:
            raise RuntimeError(f"token_account {account_id} not found")
        balance_after, reserved_after = int(account[0]), int(account[1])
        sess.execute(
            text(
                "UPDATE token_reservations SET "
                "  status = 'charged', updated_at = NOW(), finalized_at = NOW(), "
                "  metadata = COALESCE(metadata, '{}'::jsonb) || CAST(:patch AS JSONB) "
                "WHERE id = :reservation_id"
            ),
            {
                "reservation_id": reservation_id,
                "patch": _json({"job_result": result or {}}),
            },
        )
        sess.execute(
            text(
                "INSERT INTO token_ledger("
                "  token_account_id, workspace_id, crm_connection_id, job_id, reservation_id, "
                "  amount_mtokens, balance_after_mtokens, reserved_after_mtokens, kind, "
                "  description, reference, metadata) "
                "VALUES (:account_id, :workspace_id, :crm_connection_id, CAST(:job_id AS UUID), "
                "        :reservation_id, :amount, :balance_after, :reserved_after, 'charge', "
                "        'Списание токенов: первичная выгрузка amoCRM', :reference, "
                "        CAST(:metadata AS JSONB))"
            ),
            {
                "account_id": account_id,
                "workspace_id": workspace_id,
                "crm_connection_id": crm_connection_id,
                "job_id": job_row_id,
                "reservation_id": reservation_id,
                "amount": -int(amount),
                "balance_after": balance_after,
                "reserved_after": reserved_after,
                "reference": f"job:{job_row_id}",
                "metadata": _json({"reservation": metadata or {}, "job_result": result or {}}),
            },
        )


def release_token_reservation_for_job(job_row_id: str | None, error: str | None = None) -> None:
    """Release reserved AIC9 tokens after a paid job fails."""
    if not job_row_id:
        return
    with sync_session() as sess:
        row = sess.execute(
            text(
                "SELECT id, token_account_id, workspace_id, crm_connection_id, amount_mtokens "
                "FROM token_reservations "
                "WHERE job_id = CAST(:rid AS UUID) AND status = 'reserved' "
                "FOR UPDATE"
            ),
            {"rid": job_row_id},
        ).fetchone()
        if row is None:
            return
        reservation_id, account_id, workspace_id, crm_connection_id, amount = row
        account = sess.execute(
            text(
                "UPDATE token_accounts SET "
                "  reserved_mtokens = GREATEST(reserved_mtokens - :amount, 0), "
                "  updated_at = NOW() "
                "WHERE id = :account_id "
                "RETURNING balance_mtokens, reserved_mtokens"
            ),
            {"amount": int(amount), "account_id": account_id},
        ).fetchone()
        if account is None:
            raise RuntimeError(f"token_account {account_id} not found")
        balance_after, reserved_after = int(account[0]), int(account[1])
        sess.execute(
            text(
                "UPDATE token_reservations SET "
                "  status = 'released', updated_at = NOW(), finalized_at = NOW(), "
                "  metadata = COALESCE(metadata, '{}'::jsonb) || CAST(:patch AS JSONB) "
                "WHERE id = :reservation_id"
            ),
            {
                "reservation_id": reservation_id,
                "patch": _json({"error": (error or "")[:1000]}),
            },
        )
        sess.execute(
            text(
                "INSERT INTO token_ledger("
                "  token_account_id, workspace_id, crm_connection_id, job_id, reservation_id, "
                "  amount_mtokens, balance_after_mtokens, reserved_after_mtokens, kind, "
                "  description, reference, metadata) "
                "VALUES (:account_id, :workspace_id, :crm_connection_id, CAST(:job_id AS UUID), "
                "        :reservation_id, 0, :balance_after, :reserved_after, 'release', "
                "        'Возврат резерва токенов: выгрузка не завершилась', :reference, "
                "        CAST(:metadata AS JSONB))"
            ),
            {
                "account_id": account_id,
                "workspace_id": workspace_id,
                "crm_connection_id": crm_connection_id,
                "job_id": job_row_id,
                "reservation_id": reservation_id,
                "balance_after": balance_after,
                "reserved_after": reserved_after,
                "reference": f"job:{job_row_id}",
                "metadata": _json({"error": (error or "")[:1000]}),
            },
        )


def new_uuid() -> str:
    return str(uuid.uuid4())


def short_id() -> str:
    """8 hex-символов из md5(uuid4()) — для tenant-schema."""
    return hashlib.md5(uuid.uuid4().hex.encode()).hexdigest()[:8]


def _json(obj: Any) -> str:
    import json

    return json.dumps(obj, ensure_ascii=False, default=str)
