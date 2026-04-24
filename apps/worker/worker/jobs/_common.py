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
