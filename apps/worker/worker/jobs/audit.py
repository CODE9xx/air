"""
Audit jobs: генерит mock-отчёт по CRM-аккаунту с прогрессом.

Числа — из требований MVP (Brief 3, see AGENT_BRIEFS.md):
  deals=12450, contacts=8300, companies=1240, tasks=18700, notes=50300,
  messages=43000, calls=5200, call_minutes=18700, pipelines=4, users=38,
  storage_mb=2048, export_time_minutes=135, export_price=18500 RUB.
"""
from __future__ import annotations

import time
from typing import Any

from ._common import mark_job_failed, mark_job_running, mark_job_succeeded

AUDIT_RESULT: dict[str, Any] = {
    "deals_count": 12450,
    "contacts_count": 8300,
    "companies_count": 1240,
    "tasks_count": 18700,
    "notes_count": 50300,
    "messages_count": 43000,
    "calls_count": 5200,
    "call_minutes": 18700,
    "pipelines_count": 4,
    "users_count": 38,
    "estimated_storage_mb": 2048,
    "estimated_export_time_minutes": 135,
    "estimated_export_price": 18500,
    "currency": "RUB",
}


def run_audit_report(
    connection_id: str,
    *,
    job_row_id: str | None = None,
) -> dict[str, Any]:
    """Mock аудит: имитирует прогресс 0→25→60→100 и возвращает AUDIT_RESULT."""
    mark_job_running(job_row_id)
    try:
        for progress in (0, 25, 60, 100):
            print(
                f"[run_audit_report] connection={connection_id} progress={progress}%",
                flush=True,
            )
            if progress < 100:
                time.sleep(0.5)

        result = {
            "connection_id": connection_id,
            **AUDIT_RESULT,
        }
        mark_job_succeeded(job_row_id, result)
        return result
    except Exception as exc:
        mark_job_failed(job_row_id, f"run_audit_report: {exc}")
        raise
