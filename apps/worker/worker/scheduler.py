"""
Retention-scheduler.

Два режима:

1. **MVP (default, без лишних зависимостей)** — простой daily-loop:
   ``python -m worker.scheduler`` работает как отдельный процесс,
   раз в 24 часа enqueue'ит retention-job'ы в очередь ``retention``.
   Подходит для одиночного инстанса worker'а — точность ±1 секунда от старта.

2. **V1 (опц.)** — если установлен ``rq-scheduler`` и выставлен
   ``SCHEDULER_MODE=rq``, регистрируем cron-задачи:
   - ``retention_warning_daily`` 03:00 UTC
   - ``retention_read_only_daily`` 03:15 UTC
   - ``retention_delete_daily`` 04:00 UTC

Сами daily-функции находят подходящие connection_id по статусу/дням простоя
и enqueue'ят соответствующие ``retention_*`` job'ы (см. ``worker/jobs/retention.py``).

**docker-compose:** отдельный service **не добавлен** в MVP
(см. ``apps/worker/README.md``), TODO для V1.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import signal
import sys
import time
import uuid
from typing import Any

from redis import Redis
from rq import Queue
from sqlalchemy import text

from worker.lib.db import sync_session
from worker.lib.queues import QUEUE_CRM, QUEUE_RETENTION

try:
    from rq_scheduler import Scheduler  # type: ignore

    _HAS_RQ_SCHEDULER = True
except ImportError:  # pragma: no cover
    Scheduler = None  # type: ignore
    _HAS_RQ_SCHEDULER = False


REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
SCHEDULER_MODE = os.getenv("SCHEDULER_MODE", "loop")  # loop | rq
TICK_SECONDS = int(os.getenv("SCHEDULER_TICK_SECONDS", "60"))
RETENTION_INTERVAL_SECONDS = int(
    os.getenv("SCHEDULER_RETENTION_INTERVAL_SECONDS", str(24 * 60 * 60))
)
CRM_AUTO_SYNC_ENABLED = os.getenv("CRM_AUTO_SYNC_ENABLED", "true").lower() == "true"

_PLAN_SYNC_CADENCE_SECONDS: dict[str, int] = {
    "manual": 24 * 60 * 60,
    "free": 24 * 60 * 60,
    "start": 24 * 60 * 60,
    "team": 60 * 60,
    "pro": 15 * 60,
    "enterprise": 15 * 60,
}

# ---------------------------------------------------------------------------
# Daily aggregate jobs — запускаются внутри очереди retention.
# ---------------------------------------------------------------------------


def _utcnow_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def retention_warning_daily() -> dict[str, Any]:
    """
    Aggregated retention-warning tick.

    MVP: логирует факт; конкретные connections — в V1 (проход по
    ``crm_connections`` с фильтром по дням простоя).
    """
    print(f"[scheduler] retention_warning_daily ts={_utcnow_iso()}", flush=True)
    return {"ok": True, "ts": _utcnow_iso()}


def retention_read_only_daily() -> dict[str, Any]:
    """Aggregated read-only tick (день 30)."""
    print(f"[scheduler] retention_read_only_daily ts={_utcnow_iso()}", flush=True)
    return {"ok": True, "ts": _utcnow_iso()}


def retention_delete_daily() -> dict[str, Any]:
    """Aggregated retention_delete tick (день 90)."""
    print(f"[scheduler] retention_delete_daily ts={_utcnow_iso()}", flush=True)
    return {"ok": True, "ts": _utcnow_iso()}


def _parse_utc(value: Any) -> dt.datetime | None:
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _last_pull_iso(metadata: Any, last_sync_at: Any) -> str | None:
    meta = metadata if isinstance(metadata, dict) else {}
    last_pull = _parse_utc(meta.get("last_pull_at"))
    if last_pull:
        return last_pull.isoformat()
    fallback = _parse_utc(last_sync_at)
    return fallback.isoformat() if fallback else None


def _plan_cadence_seconds(plan_key: Any) -> int:
    key = str(plan_key or "free").lower()
    return _PLAN_SYNC_CADENCE_SECONDS.get(key, _PLAN_SYNC_CADENCE_SECONDS["free"])


def _has_active_pull_job(sess: Any, connection_id: str) -> bool:
    value = sess.execute(
        text(
            "SELECT COUNT(*) FROM jobs "
            "WHERE crm_connection_id = CAST(:cid AS UUID) "
            "  AND kind = 'pull_amocrm_core' "
            "  AND status IN ('queued', 'running')"
        ),
        {"cid": connection_id},
    ).scalar()
    return int(value or 0) > 0


def enqueue_due_crm_syncs(redis_conn: Redis | None = None) -> int:
    """Enqueue due incremental amoCRM sync jobs based on workspace token plan."""
    if not CRM_AUTO_SYNC_ENABLED:
        return 0

    now = dt.datetime.now(dt.timezone.utc)
    queue = Queue(QUEUE_CRM, connection=redis_conn or Redis.from_url(REDIS_URL))
    enqueued = 0

    with sync_session() as sess:
        rows = sess.execute(
            text(
                "SELECT c.id::text, c.workspace_id::text, c.metadata, c.last_sync_at, "
                "       COALESCE(ta.plan_key, 'free') AS plan_key "
                "FROM crm_connections c "
                "LEFT JOIN token_accounts ta ON ta.workspace_id = c.workspace_id "
                "WHERE c.provider = 'amocrm' "
                "  AND c.status = 'active' "
                "  AND c.tenant_schema IS NOT NULL "
                "  AND c.metadata ? 'last_pull_at'"
            )
        ).fetchall()

        for connection_id, workspace_id, metadata, last_sync_at, plan_key in rows:
            since_iso = _last_pull_iso(metadata, last_sync_at)
            since_dt = _parse_utc(since_iso)
            if since_iso is None or since_dt is None:
                continue
            cadence_seconds = _plan_cadence_seconds(plan_key)
            if now - since_dt < dt.timedelta(seconds=cadence_seconds):
                continue
            if _has_active_pull_job(sess, connection_id):
                continue

            payload = {
                "connection_id": connection_id,
                "first_pull": False,
                "since_iso": since_iso,
                "cleanup_trial": False,
                "auto_sync": True,
            }
            job_id = str(uuid.uuid4())
            sess.execute(
                text(
                    "INSERT INTO jobs("
                    "  id, workspace_id, crm_connection_id, kind, queue, status, payload"
                    ") VALUES ("
                    "  CAST(:id AS UUID), CAST(:workspace_id AS UUID), "
                    "  CAST(:connection_id AS UUID), 'pull_amocrm_core', 'crm', "
                    "  'queued', CAST(:payload AS JSONB)"
                    ")"
                ),
                {
                    "id": job_id,
                    "workspace_id": workspace_id,
                    "connection_id": connection_id,
                    "payload": json.dumps(payload, ensure_ascii=False),
                },
            )
            rq_job = queue.enqueue_call(
                func="worker.jobs.crm_pull.pull_amocrm_core",
                kwargs={**payload, "job_row_id": job_id},
                job_id=str(uuid.uuid4()),
                timeout=3600,
            )
            sess.execute(
                text("UPDATE jobs SET rq_job_id = :rqid WHERE id = CAST(:id AS UUID)"),
                {"id": job_id, "rqid": rq_job.id},
            )
            enqueued += 1

    if enqueued:
        print(f"[scheduler] enqueued crm auto-sync jobs count={enqueued}", flush=True)
    return enqueued


# ---------------------------------------------------------------------------
# MVP-loop
# ---------------------------------------------------------------------------


_RUNNING = True


def _sigterm_handler(_sig: int, _frm: Any) -> None:  # noqa: ARG001
    global _RUNNING
    _RUNNING = False
    print("[scheduler] SIGTERM/SIGINT — graceful shutdown", flush=True)


def run_loop(tick_seconds: int = TICK_SECONDS) -> int:
    """Simple loop: enqueue daily retention aggregates and due CRM sync jobs."""
    redis_conn = Redis.from_url(REDIS_URL)
    retention_queue = Queue(QUEUE_RETENTION, connection=redis_conn)

    signal.signal(signal.SIGTERM, _sigterm_handler)
    signal.signal(signal.SIGINT, _sigterm_handler)

    print(
        f"[scheduler] старт MVP-loop redis={REDIS_URL} tick={tick_seconds}s",
        flush=True,
    )

    next_retention_at = 0.0
    while _RUNNING:
        now_monotonic = time.monotonic()
        try:
            if now_monotonic >= next_retention_at:
                today = dt.datetime.now(dt.timezone.utc).date().isoformat()
                retention_queue.enqueue(
                    "worker.scheduler.retention_warning_daily",
                    job_id=f"retention_warning_daily:{today}",
                )
                retention_queue.enqueue(
                    "worker.scheduler.retention_read_only_daily",
                    job_id=f"retention_read_only_daily:{today}",
                )
                retention_queue.enqueue(
                    "worker.scheduler.retention_delete_daily",
                    job_id=f"retention_delete_daily:{today}",
                )
                next_retention_at = now_monotonic + RETENTION_INTERVAL_SECONDS
                print(f"[scheduler] enqueued daily retention-jobs ts={_utcnow_iso()}", flush=True)
            enqueue_due_crm_syncs(redis_conn)
        except Exception as exc:  # pragma: no cover — сбои Redis
            print(f"[scheduler] enqueue error: {exc}", flush=True)

        # Спим частями по 1 секунде, чтобы реагировать на SIGTERM.
        slept = 0
        while _RUNNING and slept < tick_seconds:
            time.sleep(1)
            slept += 1

    print("[scheduler] остановлен", flush=True)
    return 0


# ---------------------------------------------------------------------------
# rq-scheduler режим (V1, опционально)
# ---------------------------------------------------------------------------


def register_rq_scheduler() -> int:
    if not _HAS_RQ_SCHEDULER:
        print(
            "[scheduler] rq-scheduler не установлен. "
            "Переключитесь на SCHEDULER_MODE=loop или добавьте rq-scheduler в deps.",
            flush=True,
        )
        return 1

    redis_conn = Redis.from_url(REDIS_URL)
    scheduler = Scheduler(queue_name=QUEUE_RETENTION, connection=redis_conn)  # type: ignore[misc]

    for job in list(scheduler.get_jobs()):
        if job.id in (
            "retention_warning_daily",
            "retention_read_only_daily",
            "retention_delete_daily",
        ):
            scheduler.cancel(job)

    scheduler.cron(
        "0 3 * * *",
        func=retention_warning_daily,
        id="retention_warning_daily",
        queue_name=QUEUE_RETENTION,
        timeout=3600,
    )
    scheduler.cron(
        "15 3 * * *",
        func=retention_read_only_daily,
        id="retention_read_only_daily",
        queue_name=QUEUE_RETENTION,
        timeout=3600,
    )
    scheduler.cron(
        "0 4 * * *",
        func=retention_delete_daily,
        id="retention_delete_daily",
        queue_name=QUEUE_RETENTION,
        timeout=3600,
    )
    print("[scheduler] rq-scheduler cron-задачи зарегистрированы", flush=True)
    return 0


def main() -> int:
    if SCHEDULER_MODE == "rq":
        return register_rq_scheduler()
    return run_loop()


if __name__ == "__main__":
    sys.exit(main())
