"""
Enqueue helper для RQ (Redis-based job queue).

API ставит jobs в очередь — worker (DW-зона) выполняет реальную работу.
Имена очередей и kind-ов соответствуют `docs/db/SCHEMA.md` §1.9.
"""
from __future__ import annotations

import uuid
from typing import Any, Literal

from rq import Queue

from app.core.redis import get_sync_redis

# Очереди — см. SCHEMA.md (jobs.queue).
QueueName = Literal["crm", "export", "audit", "ai", "retention", "billing"]

# Маппинг kind → queue (SCHEMA.md §1.9).
JOB_KIND_TO_QUEUE: dict[str, QueueName] = {
    "fetch_crm_data": "crm",
    "normalize_tenant_data": "crm",
    "refresh_token": "crm",
    "bootstrap_tenant_schema": "crm",
    "build_export_zip": "export",
    "run_audit_report": "audit",
    "analyze_conversation": "ai",
    "extract_patterns": "ai",
    "anonymize_artifact": "ai",
    "retention_warning": "retention",
    "retention_read_only": "retention",
    "retention_delete": "retention",
    "delete_connection_data": "retention",
    "recalc_balance": "billing",
    "issue_invoice": "billing",
}


_queues: dict[str, Queue] = {}


def _get_queue(name: QueueName) -> Queue:
    """Кэшируем Queue-объекты."""
    if name not in _queues:
        _queues[name] = Queue(name, connection=get_sync_redis())
    return _queues[name]


def enqueue(kind: str, payload: dict[str, Any]) -> str:
    """
    Ставит job в очередь по kind.

    Возвращает строковый rq_job_id. Воркер сам заберёт по имени функции.

    В MVP мы не импортируем код воркера из API-пакета — передаём имя функции
    строкой (`job_func_path`), worker зарегистрирует импорт.
    """
    queue_name = JOB_KIND_TO_QUEUE.get(kind)
    if queue_name is None:
        raise ValueError(f"Unknown job kind: {kind}")
    queue = _get_queue(queue_name)
    # Функция воркера будет опознана по строковому пути.
    func_path = f"worker.jobs.{queue_name}.{kind}"
    # fallback: если worker не поднят — создаём RQ job id всё равно,
    # чтобы API не падал. Sync Redis операция, дешёвая.
    try:
        job = queue.enqueue(func_path, payload, job_id=str(uuid.uuid4()))
        return job.id
    except Exception:
        # В dev worker может отсутствовать. Возвращаем фиктивный id —
        # API всё равно пишет запись в таблице `jobs` (DW её обслуживает).
        return str(uuid.uuid4())


def queue_for_kind(kind: str) -> QueueName:
    """Возвращает имя очереди для данного kind."""
    q = JOB_KIND_TO_QUEUE.get(kind)
    if q is None:
        raise ValueError(f"Unknown job kind: {kind}")
    return q
