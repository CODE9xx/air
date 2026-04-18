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
import os
import signal
import sys
import time
from typing import Any

from redis import Redis
from rq import Queue

from worker.lib.queues import QUEUE_RETENTION

try:
    from rq_scheduler import Scheduler  # type: ignore

    _HAS_RQ_SCHEDULER = True
except ImportError:  # pragma: no cover
    Scheduler = None  # type: ignore
    _HAS_RQ_SCHEDULER = False


REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
SCHEDULER_MODE = os.getenv("SCHEDULER_MODE", "loop")  # loop | rq
TICK_SECONDS = int(os.getenv("SCHEDULER_TICK_SECONDS", str(24 * 60 * 60)))

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


# ---------------------------------------------------------------------------
# MVP-loop
# ---------------------------------------------------------------------------


_RUNNING = True


def _sigterm_handler(_sig: int, _frm: Any) -> None:  # noqa: ARG001
    global _RUNNING
    _RUNNING = False
    print("[scheduler] SIGTERM/SIGINT — graceful shutdown", flush=True)


def run_loop(tick_seconds: int = TICK_SECONDS) -> int:
    """Simple daily-loop: enqueue retention aggregates → sleep tick_seconds."""
    redis_conn = Redis.from_url(REDIS_URL)
    queue = Queue(QUEUE_RETENTION, connection=redis_conn)

    signal.signal(signal.SIGTERM, _sigterm_handler)
    signal.signal(signal.SIGINT, _sigterm_handler)

    print(
        f"[scheduler] старт MVP-loop redis={REDIS_URL} tick={tick_seconds}s",
        flush=True,
    )

    while _RUNNING:
        try:
            queue.enqueue(retention_warning_daily, job_id="retention_warning_daily")
            queue.enqueue(retention_read_only_daily, job_id="retention_read_only_daily")
            queue.enqueue(retention_delete_daily, job_id="retention_delete_daily")
            print(f"[scheduler] enqueued daily retention-jobs ts={_utcnow_iso()}", flush=True)
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
