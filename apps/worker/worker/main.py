"""
Code9 Analytics — точка входа фонового worker'а (RQ).

Слушает очереди из SCHEMA.md (``jobs.queue`` CHECK):
  ``default, crm, export, audit, ai, retention, billing``.

Queue-set настраивается через env ``WORKER_QUEUES`` (через запятую). По
умолчанию — все 7.

Graceful shutdown по SIGTERM/SIGINT реализован самим RQ.
"""
from __future__ import annotations

import os
import signal
import sys
from typing import Iterable

from redis import Redis
from rq import Connection, Queue, Worker

# Регистрируем все jobs ЧЕРЕЗ импорт пакета — это подтягивает зависимости
# (в частности, правильные Python-пути при вызове через RQ).
from worker.jobs import JOBS  # noqa: F401

APP_ENV = os.getenv("APP_ENV", "development")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
DEFAULT_QUEUES = "default,crm,export,audit,ai,retention,billing"
WORKER_NAME = os.getenv("WORKER_NAME")


def _parse_queues() -> list[str]:
    raw = os.getenv("WORKER_QUEUES", DEFAULT_QUEUES)
    return [q.strip() for q in raw.split(",") if q.strip()]


def main() -> int:
    queues = _parse_queues()
    print(
        f"[worker] старт env={APP_ENV} redis={REDIS_URL} queues={queues}",
        flush=True,
    )

    redis_conn = Redis.from_url(REDIS_URL)

    # RQ сам обрабатывает SIGTERM/SIGINT как graceful shutdown.
    with Connection(redis_conn):
        queue_objs: Iterable[Queue] = [Queue(name=q) for q in queues]
        worker = Worker(queue_objs, name=WORKER_NAME)
        worker.work(with_scheduler=False)

    print("[worker] остановлен", flush=True)
    return 0


if __name__ == "__main__":
    # Дополнительная защита, если RQ-handler не перехватит сигнал при старте.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    sys.exit(main())
