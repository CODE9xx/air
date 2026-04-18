"""
Retention jobs: warning → read_only → delete.

См. ``docs/security/RETENTION_POLICY.md``. Календарь:
- день 7/60/75/85 — warning notifications;
- день 30 — read-only;
- день 90 — delete_connection_data.

Эти job'ы запускаются по расписанию (rq-scheduler, см. ``worker/scheduler.py``)
а также могут быть вызваны вручную для конкретного connection_id.

LEAD-001 (2026-04-18): BE enqueue строит путь ``worker.jobs.retention.delete_connection_data``,
но реализация находится в ``delete.py``. Re-export ниже устраняет рассинхрон без изменений BE.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text

from ..lib.db import sync_session
from ._common import mark_job_failed, mark_job_running, mark_job_succeeded

# Re-export для совместимости с BE enqueue path.
# BE использует: func_path = "worker.jobs.retention.delete_connection_data"
from .delete import delete_connection_data as delete_connection_data  # noqa: F401


def _connection_ws(connection_id: str) -> tuple[str, str | None]:
    """Вернуть (workspace_id, tenant_schema) для connection."""
    with sync_session() as sess:
        row = sess.execute(
            text(
                "SELECT workspace_id, tenant_schema "
                "FROM crm_connections WHERE id = CAST(:cid AS UUID)"
            ),
            {"cid": connection_id},
        ).fetchone()
    if row is None:
        raise RuntimeError(f"connection {connection_id} не найден")
    return str(row[0]), row[1]


def retention_warning(
    connection_id: str,
    *,
    days_before: int = 30,
    job_row_id: str | None = None,
) -> dict[str, Any]:
    """Создать notification о предстоящем удалении."""
    mark_job_running(job_row_id)
    try:
        workspace_id, _ = _connection_ws(connection_id)
        title = f"Данные будут удалены через {days_before} дней"
        body = (
            "Вы можете реактивировать подключение, войдя в систему и восстановив интеграцию."
        )
        with sync_session() as sess:
            sess.execute(
                text(
                    "INSERT INTO notifications(workspace_id, kind, title, body, metadata) "
                    "VALUES (CAST(:wid AS UUID), 'retention_warning', :t, :b, CAST(:meta AS JSONB))"
                ),
                {
                    "wid": workspace_id,
                    "t": title,
                    "b": body,
                    "meta": f'{{"connection_id":"{connection_id}","days_before":{days_before}}}',
                },
            )
        result = {"connection_id": connection_id, "days_before": days_before, "notified": True}
        mark_job_succeeded(job_row_id, result)
        return result
    except Exception as exc:
        mark_job_failed(job_row_id, f"retention_warning: {exc}")
        raise


def retention_read_only(
    connection_id: str,
    *,
    job_row_id: str | None = None,
) -> dict[str, Any]:
    """Перевести connection в read-only режим (status='paused' в MVP-маппинге)."""
    mark_job_running(job_row_id)
    try:
        workspace_id, _ = _connection_ws(connection_id)
        with sync_session() as sess:
            sess.execute(
                text(
                    "UPDATE crm_connections SET status='paused', updated_at=NOW() "
                    "WHERE id = CAST(:cid AS UUID) AND status NOT IN ('deleted','deleting')"
                ),
                {"cid": connection_id},
            )
            sess.execute(
                text(
                    "INSERT INTO notifications(workspace_id, kind, title, body, metadata) "
                    "VALUES (CAST(:wid AS UUID), 'retention_read_only', "
                    "        'Подключение переведено в режим только для чтения', "
                    "        'Новые задачи синхронизации/экспорта заблокированы.', "
                    "        CAST(:meta AS JSONB))"
                ),
                {
                    "wid": workspace_id,
                    "meta": f'{{"connection_id":"{connection_id}"}}',
                },
            )
        result = {"connection_id": connection_id, "status": "paused"}
        mark_job_succeeded(job_row_id, result)
        return result
    except Exception as exc:
        mark_job_failed(job_row_id, f"retention_read_only: {exc}")
        raise


def retention_delete(
    connection_id: str,
    *,
    job_row_id: str | None = None,
) -> dict[str, Any]:
    """Финальное удаление: делегирует в ``delete_connection_data``."""
    from .delete import delete_connection_data

    return delete_connection_data(
        connection_id=connection_id,
        job_row_id=job_row_id,
    )
