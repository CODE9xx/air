"""
Deletion jobs: delete_connection_data.

См. ``docs/security/DELETION_FLOW.md``.

Алгоритм:
1. Читаем connection (FOR UPDATE).
2. Если уже deleted или tenant_schema NULL → idempotent no-op.
3. SET status='deleting'.
4. DROP SCHEMA "<name>" CASCADE (отдельная транзакция, DDL).
5. UPDATE crm_connections: status='deleted', tenant_schema=NULL, tokens=NULL.
6. UPDATE deletion_requests: status='completed' (если есть активный).
7. INSERT notifications: kind='connection_deleted'.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text

from ..lib.db import sync_session
from ._common import mark_job_failed, mark_job_running, mark_job_succeeded


def delete_connection_data(
    connection_id: str,
    *,
    job_row_id: str | None = None,
    deletion_request_id: str | None = None,
) -> dict[str, Any]:
    """Необратимое удаление подключения и всей tenant-схемы."""
    from scripts.migrations.apply_tenant_template import drop_tenant_schema

    mark_job_running(job_row_id)
    try:
        with sync_session() as sess:
            row = sess.execute(
                text(
                    "SELECT workspace_id, tenant_schema, status "
                    "FROM crm_connections WHERE id = CAST(:cid AS UUID) FOR UPDATE"
                ),
                {"cid": connection_id},
            ).fetchone()
            if row is None:
                raise RuntimeError(f"connection {connection_id} не найден")

            workspace_id, schema, status = row
            # Идемпотентность: уже deleted → no-op.
            if status == "deleted" and schema is None:
                result = {
                    "connection_id": connection_id,
                    "noop": True,
                    "reason": "уже deleted",
                }
                mark_job_succeeded(job_row_id, result)
                return result

            sess.execute(
                text(
                    "UPDATE crm_connections SET status='deleting', updated_at=NOW() "
                    "WHERE id = CAST(:cid AS UUID)"
                ),
                {"cid": connection_id},
            )

        # DROP SCHEMA — отдельная транзакция (DDL).
        if schema:
            drop_tenant_schema(schema)

        # Финальный UPDATE и notification.
        with sync_session() as sess:
            sess.execute(
                text(
                    "UPDATE crm_connections SET "
                    "  status='deleted', tenant_schema=NULL, "
                    "  access_token_encrypted=NULL, refresh_token_encrypted=NULL, "
                    "  deleted_at=NOW(), updated_at=NOW() "
                    "WHERE id = CAST(:cid AS UUID)"
                ),
                {"cid": connection_id},
            )

            if deletion_request_id:
                sess.execute(
                    text(
                        "UPDATE deletion_requests SET status='completed', "
                        "completed_at=NOW() WHERE id = CAST(:rid AS UUID)"
                    ),
                    {"rid": deletion_request_id},
                )

            sess.execute(
                text(
                    "INSERT INTO notifications(workspace_id, kind, title, body, metadata) "
                    "VALUES (CAST(:wid AS UUID), 'connection_deleted', "
                    "        'Подключение CRM удалено', "
                    "        'Все данные подключения необратимо удалены.', "
                    "        CAST(:meta AS JSONB))"
                ),
                {
                    "wid": str(workspace_id),
                    "meta": f'{{"connection_id":"{connection_id}","tenant_schema":"{schema or ""}"}}',
                },
            )

        result = {
            "connection_id": connection_id,
            "tenant_schema": schema,
            "status": "deleted",
        }
        mark_job_succeeded(job_row_id, result)
        return result
    except Exception as exc:
        mark_job_failed(job_row_id, f"delete_connection_data: {exc}")
        raise
