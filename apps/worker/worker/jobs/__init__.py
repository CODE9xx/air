"""
Регистр job-функций worker'а.

Ключи — канонические ``job_name`` (совпадают с ``JobKind`` в main-schema
и enqueue-логикой BE в ``apps/api/app/jobs/core.py``). Значения — callable.

Backend может импортировать JOBS и использовать ``job_name`` напрямую:

    from worker.jobs import JOBS
    func = JOBS["bootstrap_tenant_schema"]
    func(connection_id="...")

При изменении имён — обязательно синхронизировать с BE через
``docs/architecture/CHANGE_REQUESTS.md``.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from . import ai, audit, billing, crm, delete, export, retention

JOBS: dict[str, Callable[..., Any]] = {
    # CRM
    "bootstrap_tenant_schema": crm.bootstrap_tenant_schema,
    "refresh_token": crm.refresh_token,
    "fetch_crm_data": crm.fetch_crm_data,
    "normalize_tenant_data": crm.normalize_tenant_data,
    # Export
    "build_export_zip": export.build_export_zip,
    "trial_export": export.trial_export,
    "full_export": export.full_export,
    # Audit
    "run_audit_report": audit.run_audit_report,
    "crm_audit": audit.run_audit_report,  # alias (BE использует оба имени)
    # Deletion
    "delete_connection_data": delete.delete_connection_data,
    # Retention
    "retention_warning": retention.retention_warning,
    "retention_read_only": retention.retention_read_only,
    "retention_delete": retention.retention_delete,
    # Billing
    "billing_monthly_charge": billing.billing_monthly_charge,
    "billing_usage_charge": billing.billing_usage_charge,
    "recalc_balance": billing.recalc_balance,
    "issue_invoice": billing.issue_invoice,
    # AI
    "analyze_deals": ai.analyze_deals,
    "analyze_calls": ai.analyze_calls,
    "analyze_chats": ai.analyze_chats,
    "analyze_conversation": ai.analyze_conversation,
    "extract_patterns": ai.extract_patterns,
    "anonymize_patterns": ai.anonymize_patterns,
    "anonymize_artifact": ai.anonymize_patterns,  # alias
    "update_research_dataset": ai.update_research_dataset,
}


__all__ = ["JOBS", "crm", "export", "audit", "delete", "retention", "billing", "ai"]
