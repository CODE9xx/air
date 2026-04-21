"""
CRM-related jobs: bootstrap_tenant_schema, refresh_token, fetch_crm_data,
normalize_tenant_data.

В MOCK_CRM_MODE все внешние вызовы — мок. Шифрование токенов — через Fernet
(см. ``worker/lib/crypto.py``).

В REAL mode (``MOCK_CRM_MODE=false``):

* ``refresh_token`` — реально дёргает AmoCrmConnector.refresh, ротирует
  access+refresh и пишет encrypted токены обратно в БД.
* ``refresh_expiring_tokens_daily`` — агрегатный sweep: находит подключения
  с ``token_expires_at < now + 2h`` и enqueue'ит ``refresh_token`` для каждого.
  Вызывается из scheduler'а (см. ``worker/scheduler.py``).
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text

from ..lib.amocrm_creds import load_amocrm_oauth_credentials
from ..lib.crypto import decrypt_token, encrypt_token
from ..lib.db import sync_session
from ._common import (
    mark_job_failed,
    mark_job_running,
    mark_job_succeeded,
    short_id,
)

MOCK_CRM_MODE = os.getenv("MOCK_CRM_MODE", "true").lower() == "true"

logger = logging.getLogger("code9.worker.crm")


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

    MOCK_CRM_MODE=true: просто продлевает ``token_expires_at`` на 30 дней.
    MOCK_CRM_MODE=false + provider='amocrm':
        * decrypt refresh_token
        * AmoCrmConnector.refresh → новая пара токенов
        * encrypt + UPDATE crm_connections
        * InvalidGrant  → status='lost_token', last_error, return {invalid_grant: True}
        * ProviderError → re-raise (RQ ретраит по своей политике)
    """
    mark_job_running(job_row_id)
    try:
        with sync_session() as sess:
            # Task #52.3F (Bug F): добавлены ``amocrm_auth_mode`` +
            # ``amocrm_client_id`` + ``amocrm_client_secret_encrypted`` —
            # для external_button рефреш должен использовать
            # per-installation creds, не глобальный env.
            row = sess.execute(
                text(
                    "SELECT refresh_token_encrypted, status, provider, external_domain, "
                    "       amocrm_auth_mode, amocrm_client_id, "
                    "       amocrm_client_secret_encrypted "
                    "FROM crm_connections WHERE id = CAST(:cid AS UUID)"
                ),
                {"cid": connection_id},
            ).fetchone()
            if row is None:
                raise RuntimeError(f"connection {connection_id} не найден")

        (
            encrypted_refresh,
            status,
            provider,
            external_domain,
            amocrm_auth_mode,
            amocrm_client_id_col,
            amocrm_client_secret_encrypted,
        ) = row

        if MOCK_CRM_MODE:
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

        # ---- REAL mode ------------------------------------------------------
        if provider != "amocrm":
            raise NotImplementedError(
                f"refresh_token real mode: провайдер '{provider}' пока не поддержан "
                "(только amocrm в Phase 2A)."
            )
        if not encrypted_refresh:
            # Подключение без refresh-токена → lost_token.
            _mark_lost_token(connection_id, "refresh_token_encrypted is NULL")
            result = {"connection_id": connection_id, "invalid_grant": True, "reason": "no_refresh"}
            mark_job_succeeded(job_row_id, result)
            return result

        subdomain = _amocrm_subdomain_from_domain(external_domain)
        if not subdomain:
            _mark_lost_token(
                connection_id,
                f"external_domain='{external_domain}' — не похоже на *.amocrm.ru",
            )
            result = {"connection_id": connection_id, "invalid_grant": True, "reason": "bad_domain"}
            mark_job_succeeded(job_row_id, result)
            return result

        # Импорты тянем лениво: на dev без пакетов crm-connectors worker не падает.
        from crm_connectors.amocrm import AmoCrmConnector  # type: ignore
        from crm_connectors.exceptions import (  # type: ignore
            InvalidGrant,
            ProviderError,
            RateLimited,
            TokenExpired,
        )

        # Task #52.3F (Bug F): резолвим credentials через helper —
        # external_button → per-installation из БД, static_client/NULL →
        # env AMOCRM_CLIENT_ID/SECRET. Ошибки helper'а (missing / decrypt
        # fail / env empty) пробрасываются — НЕ превращаем в lost_token,
        # иначе config-misstep снёс бы токены пользователей.
        client_id, client_secret = load_amocrm_oauth_credentials(
            {
                "amocrm_auth_mode": amocrm_auth_mode,
                "amocrm_client_id": amocrm_client_id_col,
                "amocrm_client_secret_encrypted": amocrm_client_secret_encrypted,
            },
            connection_id=connection_id,
        )

        old_refresh = decrypt_token(encrypted_refresh)
        connector = AmoCrmConnector(
            client_id=client_id,
            client_secret=client_secret,
            subdomain=subdomain,
        )
        try:
            tokens = connector.refresh(old_refresh)
        except InvalidGrant as exc:
            logger.warning(
                "crm_refresh_invalid_grant",
                extra={"connection_id": connection_id, "provider": provider},
            )
            _mark_lost_token(connection_id, "amoCRM вернул invalid_grant")
            result = {
                "connection_id": connection_id,
                "invalid_grant": True,
                "reason": "amocrm_invalid_grant",
            }
            mark_job_succeeded(job_row_id, result)
            return result
        except (TokenExpired, RateLimited, ProviderError) as exc:
            # Транзиентно — бросаем дальше, RQ сам ретраит.
            logger.warning(
                "crm_refresh_transient_error",
                extra={
                    "connection_id": connection_id,
                    "error_type": type(exc).__name__,
                },
            )
            mark_job_failed(job_row_id, f"refresh_token: {type(exc).__name__}")
            raise

        # Успех: encrypt + UPDATE.
        access_enc = encrypt_token(tokens.access_token)
        refresh_enc = encrypt_token(tokens.refresh_token)

        with sync_session() as sess:
            sess.execute(
                text(
                    "UPDATE crm_connections SET "
                    "  access_token_encrypted=:access, "
                    "  refresh_token_encrypted=:refresh, "
                    "  token_expires_at=:exp, "
                    "  updated_at=NOW(), "
                    "  last_error=NULL, "
                    "  status=CASE WHEN status='lost_token' THEN 'active' ELSE status END "
                    "WHERE id=CAST(:cid AS UUID)"
                ),
                {
                    "access": access_enc,
                    "refresh": refresh_enc,
                    "exp": tokens.expires_at,
                    "cid": connection_id,
                },
            )

        logger.info(
            "crm_refresh_ok",
            extra={
                "connection_id": connection_id,
                "provider": provider,
                "expires_at": tokens.expires_at.isoformat(),
            },
        )
        result = {
            "connection_id": connection_id,
            "token_expires_at": tokens.expires_at.isoformat(),
            "mock": False,
        }
        mark_job_succeeded(job_row_id, result)
        return result
    except Exception as exc:
        mark_job_failed(job_row_id, f"refresh_token: {exc}")
        raise


def _mark_lost_token(connection_id: str, reason: str) -> None:
    """Перевести подключение в lost_token + записать last_error."""
    with sync_session() as sess:
        sess.execute(
            text(
                "UPDATE crm_connections "
                "SET status='lost_token', last_error=:err, updated_at=NOW() "
                "WHERE id=CAST(:cid AS UUID)"
            ),
            {"err": reason[:500], "cid": connection_id},
        )


def _amocrm_subdomain_from_domain(domain: str | None) -> str | None:
    """
    'foobar.amocrm.ru' → 'foobar'. На battered/None значении — None.
    """
    if not domain:
        return None
    slug = domain.strip().split(".", 1)[0].strip().lower()
    if not slug or not slug.replace("-", "").isalnum():
        return None
    return slug


def refresh_expiring_tokens_daily(
    *,
    threshold_minutes: int = 120,
    job_row_id: str | None = None,
) -> dict[str, Any]:
    """
    Агрегатный sweep: enqueue refresh_token для подключений, у которых
    ``token_expires_at < now + threshold_minutes``.

    Вызывается scheduler'ом (или крон-джобой). В MOCK режиме тоже работает —
    просто мок-refresh удлиняет expiry на 30 дней, что делает следующий tick no-op.
    """
    from rq import Queue
    from redis import Redis

    mark_job_running(job_row_id)
    try:
        cutoff = datetime.now(timezone.utc) + timedelta(minutes=threshold_minutes)
        with sync_session() as sess:
            rows = sess.execute(
                text(
                    "SELECT id FROM crm_connections "
                    "WHERE deleted_at IS NULL "
                    "  AND status IN ('active','connecting') "
                    "  AND token_expires_at IS NOT NULL "
                    "  AND token_expires_at < :cutoff"
                ),
                {"cutoff": cutoff},
            ).fetchall()
        connection_ids = [str(r[0]) for r in rows]

        if connection_ids:
            redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
            queue = Queue("crm", connection=Redis.from_url(redis_url))
            for cid in connection_ids:
                queue.enqueue("worker.jobs.crm.refresh_token", cid)

        result = {
            "enqueued": len(connection_ids),
            "cutoff": cutoff.isoformat(),
        }
        logger.info("crm_refresh_sweep", extra=result)
        mark_job_succeeded(job_row_id, result)
        return result
    except Exception as exc:
        mark_job_failed(job_row_id, f"refresh_expiring_tokens_daily: {exc}")
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
