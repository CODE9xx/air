"""
CRM-related jobs: bootstrap_tenant_schema, refresh_token, fetch_crm_data,
normalize_tenant_data.

В MVP все внешние вызовы — мок. Шифрование токенов — через Fernet (см.
``worker/lib/crypto.py``).
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text

from ..lib.crypto import decrypt_token
from ..lib.db import sync_session
from ._common import (
    mark_job_failed,
    mark_job_running,
    mark_job_succeeded,
    short_id,
)

MOCK_CRM_MODE = os.getenv("MOCK_CRM_MODE", "true").lower() == "true"


# ---------------------------------------------------------------------------
# bootstrap_tenant_schema
# ---------------------------------------------------------------------------

def bootstrap_tenant_schema(
    connection_id: str,
    *,
    job_row_id: str | None = None,
) -> dict[str, Any]:
    """
    Создать tenant-схему для connection и выставить ``crm_connections.tenant_schema``.

    Идемпотентна: если ``tenant_schema`` уже не NULL — просто reapply миграции
    (что is no-op, т.к. alembic видит актуальный head) и выходит.
    """
    from scripts.migrations.apply_tenant_template import apply_tenant_template

    mark_job_running(job_row_id)
    try:
        with sync_session() as sess:
            row = sess.execute(
                text(
                    "SELECT tenant_schema, provider, status FROM crm_connections "
                    "WHERE id = CAST(:cid AS UUID) FOR UPDATE"
                ),
                {"cid": connection_id},
            ).fetchone()
            if row is None:
                raise RuntimeError(f"connection {connection_id} не найден")

            existing_schema, provider, status = row
            if status == "deleted":
                raise RuntimeError("нельзя создавать схему для удалённого connection")

            schema = existing_schema
            if not schema:
                provider_slug = {
                    "amocrm": "amo",
                    "kommo": "kommo",
                    "bitrix24": "bx24",
                }.get(provider, "crm")
                schema = f"crm_{provider_slug}_{short_id()}"

            # Обновляем БД с именем ДО DDL, чтобы job был идемпотентным на ретраях.
            sess.execute(
                text(
                    "UPDATE crm_connections SET tenant_schema=:schema, "
                    "status=CASE WHEN status='pending' THEN 'connecting' ELSE status END, "
                    "updated_at=NOW() WHERE id=CAST(:cid AS UUID)"
                ),
                {"schema": schema, "cid": connection_id},
            )

        # Apply tenant template (CREATE SCHEMA + alembic upgrade).
        apply_tenant_template(schema)

        # Переводим в active, если сейчас connecting.
        with sync_session() as sess:
            sess.execute(
                text(
                    "UPDATE crm_connections "
                    "SET status=CASE WHEN status IN ('pending','connecting') "
                    "              THEN 'active' ELSE status END, "
                    "    updated_at=NOW() "
                    "WHERE id=CAST(:cid AS UUID)"
                ),
                {"cid": connection_id},
            )

        result = {"connection_id": connection_id, "tenant_schema": schema, "status": "ok"}
        mark_job_succeeded(job_row_id, result)
        return result
    except Exception as exc:
        mark_job_failed(job_row_id, f"bootstrap_tenant_schema: {exc}")
        raise


# ---------------------------------------------------------------------------
# refresh_token
# ---------------------------------------------------------------------------

def refresh_token(
    connection_id: str,
    *,
    job_row_id: str | None = None,
) -> dict[str, Any]:
    """
    Refresh OAuth-токена.

    В MOCK_CRM_MODE просто продлевает ``token_expires_at`` на 30 дней.
    В реальном режиме — NotImplementedError (MVP не делает реальных вызовов).
    """
    mark_job_running(job_row_id)
    try:
        with sync_session() as sess:
            row = sess.execute(
                text(
                    "SELECT refresh_token_encrypted, status "
                    "FROM crm_connections WHERE id = CAST(:cid AS UUID)"
                ),
                {"cid": connection_id},
            ).fetchone()
            if row is None:
                raise RuntimeError(f"connection {connection_id} не найден")

        encrypted_refresh, status = row

        if not MOCK_CRM_MODE:
            # В реальном режиме сюда стучимся в amoCRM/Kommo/Bitrix.
            # В MVP этого нет — осознанно.
            if encrypted_refresh:
                _ = decrypt_token(encrypted_refresh)  # pragma: no cover
            raise NotImplementedError(
                "Реальный refresh_token не реализован в MVP — только MOCK_CRM_MODE"
            )

        new_expiry = datetime.now(timezone.utc) + timedelta(days=30)
        with sync_session() as sess:
            sess.execute(
                text(
                    "UPDATE crm_connections "
                    "SET token_expires_at=:exp, updated_at=NOW(), "
                    "    status=CASE WHEN status='lost_token' THEN 'active' ELSE status END "
                    "WHERE id=CAST(:cid AS UUID)"
                ),
                {"exp": new_expiry, "cid": connection_id},
            )

        result = {
            "connection_id": connection_id,
            "token_expires_at": new_expiry.isoformat(),
            "mock": True,
        }
        mark_job_succeeded(job_row_id, result)
        return result
    except Exception as exc:
        mark_job_failed(job_row_id, f"refresh_token: {exc}")
        raise


# ---------------------------------------------------------------------------
# fetch_crm_data / normalize_tenant_data — в MVP заглушки с прогрессом
# ---------------------------------------------------------------------------

def fetch_crm_data(
    connection_id: str,
    *,
    job_row_id: str | None = None,
    since: str | None = None,
) -> dict[str, Any]:
    """Заглушка fetch-цикла в MVP: делегирует trial_export и обновляет last_sync_at."""
    from .export import trial_export

    mark_job_running(job_row_id)
    try:
        export_result = trial_export(connection_id=connection_id, job_row_id=None)

        with sync_session() as sess:
            sess.execute(
                text(
                    "UPDATE crm_connections SET last_sync_at=NOW(), updated_at=NOW() "
                    "WHERE id=CAST(:cid AS UUID)"
                ),
                {"cid": connection_id},
            )

        result = {"connection_id": connection_id, "since": since, "export": export_result}
        mark_job_succeeded(job_row_id, result)
        return result
    except Exception as exc:
        mark_job_failed(job_row_id, f"fetch_crm_data: {exc}")
        raise


def normalize_tenant_data(
    connection_id: str,
    *,
    job_row_id: str | None = None,
) -> dict[str, Any]:
    """
    Нормализация raw_* → структурированные таблицы.

    В MVP нормализация выполняется прямо в trial_export, поэтому здесь —
    лёгкая прокладка с прогрессом, чтобы UI мог наблюдать статус.
    """
    mark_job_running(job_row_id)
    try:
        for step in (0, 33, 66, 100):
            # простое логирование прогресса
            print(f"[normalize_tenant_data] {connection_id} progress={step}%", flush=True)
            if step < 100:
                time.sleep(0.2)
        result = {"connection_id": connection_id, "normalized": True}
        mark_job_succeeded(job_row_id, result)
        return result
    except Exception as exc:
        mark_job_failed(job_row_id, f"normalize_tenant_data: {exc}")
        raise
