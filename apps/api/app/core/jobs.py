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
    # Phase 2A: pull_amocrm_core живёт в worker.jobs.crm_pull —
    # см. JOB_KIND_TO_MODULE ниже.
    "pull_amocrm_core": "crm",
    "pull_email_imap": "crm",
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

# Маппинг kind → имя подмодуля ``worker.jobs.<module>``, если оно НЕ совпадает
# с именем очереди. По умолчанию func_path = ``worker.jobs.<queue>.<kind>``;
# здесь перечисляем исключения — функция лежит не в одноимённом модуле.
JOB_KIND_TO_MODULE: dict[str, str] = {
    "pull_amocrm_core": "crm_pull",
    "pull_email_imap": "email_pull",
}

JOB_KIND_TIMEOUT_SECONDS: dict[str, int] = {
    # Full-period amoCRM pulls can process tens of thousands of deals.
    # RQ default is 180s, which is too small for the real export flow.
    "pull_amocrm_core": 3600,
    "pull_email_imap": 7200,
}


_queues: dict[str, Queue] = {}


def _get_queue(name: QueueName) -> Queue:
    """Кэшируем Queue-объекты."""
    if name not in _queues:
        _queues[name] = Queue(name, connection=get_sync_redis())
    return _queues[name]


def enqueue(
    kind: str,
    payload: dict[str, Any],
    *,
    depends_on: str | None = None,
    job_row_id: str | None = None,
) -> str:
    """
    Ставит job в очередь по kind.

    Возвращает строковый rq_job_id. Воркер сам заберёт по имени функции.

    В MVP мы не импортируем код воркера из API-пакета — передаём имя функции
    строкой (`job_func_path`), worker зарегистрирует импорт.

    ``depends_on`` — rq_job_id другого job'а, после успешного выполнения которого
    запустится текущий (Phase 2A: bootstrap_tenant_schema → pull_amocrm_core).

    ``job_row_id`` — UUID записи в ``public.jobs``. Если передан, попадает
    в worker kwargs под ключом ``job_row_id``; воркер использует его
    в ``mark_job_running``/``mark_job_succeeded``/``mark_job_failed``
    для обновления ``public.jobs.status`` и ``result``/``error``.

    **Важно (Task #52.6):** ``job_row_id`` кладётся ТОЛЬКО в worker kwargs,
    переданные в RQ (через shallow copy ``payload``). Исходный ``payload``
    dict не мутируется — вызывающий код хранит его в ``public.jobs.payload``
    в исходном виде (без ``job_row_id``, чтобы не дублировать id в двух
    колонках). Контракт зафиксирован в
    ``tests/api/test_jobs_enqueue.py``.

    До Task #52.6 ``enqueue()`` не принимал ``job_row_id``, воркер получал
    ``job_row_id=None`` через default, и ``mark_job_*`` тихо no-op'ил
    (``if not job_row_id: return``) — статус в ``public.jobs`` вечно
    болтался в ``queued``.
    """
    queue_name = JOB_KIND_TO_QUEUE.get(kind)
    if queue_name is None:
        raise ValueError(f"Unknown job kind: {kind}")
    queue = _get_queue(queue_name)
    # Функция воркера будет опознана по строковому пути.
    module = JOB_KIND_TO_MODULE.get(kind, queue_name)
    func_path = f"worker.jobs.{module}.{kind}"
    # Bug D (Task #52.3D, обнаружен в live-прогоне #52.3 после фикса Bug C):
    # ранее использовалось ``queue.enqueue(func_path, payload, **enqueue_kwargs)``,
    # что заставляло RQ класть payload dict как ПЕРВЫЙ ПОЗИЦИОННЫЙ аргумент
    # в worker-функцию. Все worker-jobs имеют сигнатуру
    # ``def job(<entity>_id: str, *, ...)``, и dict попадал на место
    # ``connection_id``/``workspace_id``/``billing_account_id``/``text_in``,
    # что ломалось либо на psycopg2 ``can't adapt type 'dict'``, либо
    # глубже в функции. Правильный API — ``queue.enqueue_call`` с явным
    # ``kwargs=payload``: RQ распаковывает dict как kwargs, имена совпадают
    # с параметрами функции (см. signature inventory в tests/api/test_jobs_enqueue.py).
    #
    # fallback: если worker не поднят — создаём RQ job id всё равно,
    # чтобы API не падал. Sync Redis операция, дешёвая.
    try:
        # Shallow copy: добавляем job_row_id только в worker-kwargs,
        # не трогая исходный payload (он идёт в public.jobs.payload как есть).
        worker_kwargs: dict[str, Any] = dict(payload)
        if job_row_id is not None:
            worker_kwargs["job_row_id"] = job_row_id
        enqueue_kwargs: dict[str, Any] = {"job_id": str(uuid.uuid4())}
        if kind in JOB_KIND_TIMEOUT_SECONDS:
            enqueue_kwargs["timeout"] = JOB_KIND_TIMEOUT_SECONDS[kind]
        if depends_on:
            enqueue_kwargs["depends_on"] = depends_on
        job = queue.enqueue_call(
            func=func_path, kwargs=worker_kwargs, **enqueue_kwargs
        )
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
