"""
Константы имён очередей RQ.

Единая точка правды для имён очередей; совпадают со значениями ``JobQueue``
в ``apps/api/app/db/models/enums.py`` и CHECK-констрейнтом на ``jobs.queue``
в main schema.

Любое изменение — только через CR с BE (enum ``JobQueue``) и миграцию
CHECK-констрейнта. См. ``docs/db/SCHEMA.md`` §1.9.
"""
from __future__ import annotations

from typing import Final

# Очереди (6 бизнес-очередей + служебная default).
QUEUE_CRM: Final = "crm"
QUEUE_EXPORT: Final = "export"
QUEUE_AUDIT: Final = "audit"
QUEUE_AI: Final = "ai"
QUEUE_RETENTION: Final = "retention"
QUEUE_BILLING: Final = "billing"
QUEUE_DEFAULT: Final = "default"

# Порядок совпадает с приоритетом обработки в worker.main (env WORKER_QUEUES).
ALL_QUEUES: Final[tuple[str, ...]] = (
    QUEUE_DEFAULT,
    QUEUE_CRM,
    QUEUE_EXPORT,
    QUEUE_AUDIT,
    QUEUE_AI,
    QUEUE_RETENTION,
    QUEUE_BILLING,
)

# Маппинг job_name → очередь (для BE enqueue-логики).
# Источник правды: ``docs/db/SCHEMA.md`` §1.9 и ``AGENT_BRIEFS.md`` Brief 3.
JOB_TO_QUEUE: Final[dict[str, str]] = {
    # CRM
    "bootstrap_tenant_schema": QUEUE_CRM,
    "refresh_token": QUEUE_CRM,
    "fetch_crm_data": QUEUE_CRM,
    "normalize_tenant_data": QUEUE_CRM,
    # Export
    "build_export_zip": QUEUE_EXPORT,
    "trial_export": QUEUE_EXPORT,
    "full_export": QUEUE_EXPORT,
    # Audit
    "run_audit_report": QUEUE_AUDIT,
    "crm_audit": QUEUE_AUDIT,
    # Deletion и Retention
    "delete_connection_data": QUEUE_RETENTION,
    "retention_warning": QUEUE_RETENTION,
    "retention_read_only": QUEUE_RETENTION,
    "retention_delete": QUEUE_RETENTION,
    # Billing
    "billing_monthly_charge": QUEUE_BILLING,
    "billing_usage_charge": QUEUE_BILLING,
    "recalc_balance": QUEUE_BILLING,
    "issue_invoice": QUEUE_BILLING,
    # AI
    "analyze_deals": QUEUE_AI,
    "analyze_calls": QUEUE_AI,
    "analyze_chats": QUEUE_AI,
    "analyze_conversation": QUEUE_AI,
    "extract_patterns": QUEUE_AI,
    "anonymize_patterns": QUEUE_AI,
    "anonymize_artifact": QUEUE_AI,
    "update_research_dataset": QUEUE_AI,
}


def queue_for_job(job_name: str) -> str:
    """Вернуть имя очереди по имени job. Fallback — ``default``."""
    return JOB_TO_QUEUE.get(job_name, QUEUE_DEFAULT)


__all__ = [
    "QUEUE_CRM",
    "QUEUE_EXPORT",
    "QUEUE_AUDIT",
    "QUEUE_AI",
    "QUEUE_RETENTION",
    "QUEUE_BILLING",
    "QUEUE_DEFAULT",
    "ALL_QUEUES",
    "JOB_TO_QUEUE",
    "queue_for_job",
]
