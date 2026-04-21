"""
CRM pull jobs (Phase 2A step 5).

Основной entry-point: ``pull_amocrm_core(connection_id, first_pull=False)``.

Что делает:

1. Читает ``crm_connections`` (access_token_encrypted, refresh_token_encrypted,
   token_expires_at, tenant_schema, external_domain).
2. При необходимости рефрешит access_token (inline вызов ``refresh_token``),
   если до экспирации осталось ≤ 120s.
3. Инстанцирует ``AmoCrmConnector(client_id, client_secret, subdomain)``.
4. Качает 4 ядра в строгом порядке (зависимости FK):
   pipelines → stages → users → contacts → deals.
5. Каждая сущность UPSERT'ится в raw_* + нормализованную таблицу
   внутри tenant-schema (search_path trick — как в ``trial_export``).
6. Ведёт in-memory маппинг ``external_id → tenant UUID`` для разрешения FK
   (stage→pipeline, deal→contact/company/user/pipeline/stage, contact→user).
7. Обновляет ``CrmConnection.last_sync_at`` и кладёт сводку в ``metadata_json``.
8. Enqueue-ит ``run_audit_report`` после успешного pull'а.

Безопасность:

* Телефон/email/ИНН — НИКОГДА не кладём в открытом виде в нормализованные
  таблицы (contacts.phone_primary_hash, contacts.email_primary_hash,
  companies.inn_hash — SHA-256 с солью из ``PII_HASH_SALT``). Оригиналы
  остаются только в ``raw_contacts.payload`` и шифруются на уровне
  backup'а (pg_dump → шифрованный archive).
* access_token в лог не попадает — логируем только connection_id и счётчики.

MOCK_CRM_MODE=true: делегируем ``trial_export`` (как раньше), потом тоже
enqueue'им audit, чтобы UI-пайплайн был одинаковым.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import uuid as uuid_mod
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from sqlalchemy import text

from ..lib.amocrm_creds import load_amocrm_oauth_credentials
from ..lib.crypto import decrypt_token
from ..lib.db import sync_session
from ._common import (
    mark_job_failed,
    mark_job_running,
    mark_job_succeeded,
)

logger = logging.getLogger("code9.worker.crm_pull")

MOCK_CRM_MODE = os.getenv("MOCK_CRM_MODE", "true").lower() == "true"

# Порог, ниже которого перед pull'ом принудительно рефрешимся inline.
_ACCESS_TOKEN_REFRESH_THRESHOLD_SECONDS = 120


# ---------------------------------------------------------------------------
# PII hashing (phone / email / inn)
# ---------------------------------------------------------------------------

_DIGITS_ONLY_RE = re.compile(r"\D+")


def _pii_salt() -> str:
    """
    Соль для SHA-256. Из env ``PII_HASH_SALT``. В dev дефолт приемлем —
    любой хеш лучше голого телефона.

    prod-валидатор (``apps/api/app/core/settings.py``) в будущем может
    добавить fail-fast если соль дефолтная — пока не требуется.
    """
    return os.getenv("PII_HASH_SALT", "code9-pii-v1")


def _hash_pii(value: str | None) -> str | None:
    """SHA-256(salt + normalized_value). None/пусто → None."""
    if not value:
        return None
    salt = _pii_salt()
    digest = hashlib.sha256((salt + value).encode("utf-8")).hexdigest()
    return digest


def _normalize_phone(raw: str | None) -> str | None:
    """
    Нормализация телефона перед хешированием.

    Правила:
    * оставляем только цифры;
    * ведущая 8 для RU номеров → 7 (чтобы '89001112233' и '+79001112233'
      давали одинаковый хеш и мы могли найти контакт).
    """
    if not raw:
        return None
    digits = _DIGITS_ONLY_RE.sub("", raw)
    if not digits:
        return None
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    return digits


def _normalize_email(raw: str | None) -> str | None:
    """Лower + trim. amoCRM сам не нормализует."""
    if not raw:
        return None
    val = raw.strip().lower()
    return val or None


# ---------------------------------------------------------------------------
# Helpers: tenant schema, token freshness
# ---------------------------------------------------------------------------

def _fetch_connection_row(connection_id: str) -> dict[str, Any]:
    """Читает нужные поля CrmConnection одним SELECT.

    Task #52.3F (Bug F): добавлены поля ``amocrm_auth_mode`` +
    ``amocrm_client_id`` + ``amocrm_client_secret_encrypted``, чтобы
    ``load_amocrm_oauth_credentials`` мог резолвить per-installation
    credentials для ``external_button`` connections (pre-#44.6
    подключения остаются на env via ``static_client`` fallback).
    """
    with sync_session() as sess:
        row = sess.execute(
            text(
                "SELECT provider, status, tenant_schema, external_domain, "
                "       access_token_encrypted, refresh_token_encrypted, "
                "       token_expires_at, "
                "       amocrm_auth_mode, amocrm_client_id, "
                "       amocrm_client_secret_encrypted "
                "FROM crm_connections "
                "WHERE id = CAST(:cid AS UUID)"
            ),
            {"cid": connection_id},
        ).fetchone()
    if row is None:
        raise RuntimeError(f"connection {connection_id} не найден")
    return {
        "provider": row[0],
        "status": row[1],
        "tenant_schema": row[2],
        "external_domain": row[3],
        "access_token_encrypted": row[4],
        "refresh_token_encrypted": row[5],
        "token_expires_at": row[6],
        "amocrm_auth_mode": row[7],
        "amocrm_client_id": row[8],
        "amocrm_client_secret_encrypted": row[9],
    }


def _ensure_fresh_access_token(conn_info: dict[str, Any], connection_id: str) -> str:
    """
    Гарантирует живой access_token. Если до экспирации ≤ 120s —
    делает inline refresh и повторно читает строку.
    """
    from .crm import refresh_token  # локальный импорт — избегаем циклов

    expires_at = conn_info.get("token_expires_at")
    need_refresh = False
    if expires_at is None:
        need_refresh = True
    else:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at - datetime.now(tz=timezone.utc) <= timedelta(
            seconds=_ACCESS_TOKEN_REFRESH_THRESHOLD_SECONDS
        ):
            need_refresh = True

    if need_refresh:
        logger.info(
            "crm_pull_inline_refresh",
            extra={"connection_id": connection_id},
        )
        result = refresh_token(connection_id=connection_id)
        if result.get("invalid_grant"):
            raise RuntimeError(
                f"refresh invalid_grant для {connection_id}: {result.get('reason')}"
            )
        # перечитываем токен
        conn_info.update(_fetch_connection_row(connection_id))

    access_enc = conn_info.get("access_token_encrypted")
    if not access_enc:
        raise RuntimeError(
            f"access_token_encrypted пуст для {connection_id} — невозможно сделать pull"
        )
    return decrypt_token(access_enc)


def _amocrm_subdomain(external_domain: str | None) -> str | None:
    """'foobar.amocrm.ru' → 'foobar'. На мусоре — None."""
    if not external_domain:
        return None
    slug = external_domain.strip().split(".", 1)[0].strip().lower()
    if not slug or not slug.replace("-", "").isalnum():
        return None
    return slug


def _uuid() -> str:
    return str(uuid_mod.uuid4())


# ---------------------------------------------------------------------------
# UPSERT helpers
# ---------------------------------------------------------------------------

def _upsert_raw(sess, table: str, external_id: str, payload: dict[str, Any]) -> None:
    """UPSERT в raw_<entity>: (external_id UNIQUE) → refresh payload + fetched_at."""
    import json

    sess.execute(
        text(
            f"INSERT INTO {table}(id, external_id, payload, fetched_at) "
            f"VALUES (CAST(:id AS UUID), :ext, CAST(:payload AS JSONB), NOW()) "
            f"ON CONFLICT (external_id) DO UPDATE SET "
            f"  payload = EXCLUDED.payload, fetched_at = NOW()"
        ),
        {
            "id": _uuid(),
            "ext": external_id,
            "payload": json.dumps(payload, ensure_ascii=False, default=str),
        },
    )


# ---------------------------------------------------------------------------
# Pull stages
# ---------------------------------------------------------------------------

def _pull_pipelines(sess, connector, access_token: str) -> dict[str, str]:
    """
    Тянет воронки. Возвращает маппинг external_id → tenant UUID.
    Используется downstream для stage.pipeline_id и deal.pipeline_id.
    """
    ext_to_uuid: dict[str, str] = {}

    for raw_p in connector.fetch_pipelines(access_token):
        ext_id = raw_p.crm_id
        if not ext_id:
            continue
        _upsert_raw(sess, "raw_pipelines", ext_id, raw_p.raw_payload)

        # UPSERT normalized. ON CONFLICT возвращает id — используем RETURNING.
        tenant_uuid = _uuid()
        result = sess.execute(
            text(
                "INSERT INTO pipelines(id, external_id, name, is_default, fetched_at) "
                "VALUES (CAST(:id AS UUID), :ext, :name, :def, NOW()) "
                "ON CONFLICT (external_id) DO UPDATE SET "
                "  name = EXCLUDED.name, is_default = EXCLUDED.is_default, fetched_at = NOW() "
                "RETURNING id"
            ),
            {
                "id": tenant_uuid,
                "ext": ext_id,
                "name": raw_p.name or "",
                "def": bool(raw_p.is_default),
            },
        )
        row = result.fetchone()
        if row and row[0]:
            ext_to_uuid[ext_id] = str(row[0])
    return ext_to_uuid


def _pull_stages(
    sess, connector, access_token: str, pipeline_map: dict[str, str]
) -> dict[str, str]:
    """Тянет этапы всех воронок. Возвращает маппинг external_id → tenant UUID."""
    ext_to_uuid: dict[str, str] = {}

    for raw_s in connector.fetch_stages(access_token):
        ext_id = raw_s.crm_id
        if not ext_id:
            continue
        pipeline_uuid = pipeline_map.get(raw_s.pipeline_id)
        if not pipeline_uuid:
            # amoCRM не должен слать статус без pipeline, но на всякий пропустим.
            continue

        _upsert_raw(sess, "raw_stages", ext_id, raw_s.raw_payload)

        tenant_uuid = _uuid()
        result = sess.execute(
            text(
                "INSERT INTO stages(id, external_id, pipeline_id, name, sort_order, kind, fetched_at) "
                "VALUES (CAST(:id AS UUID), :ext, CAST(:pid AS UUID), :name, :sort, :kind, NOW()) "
                "ON CONFLICT (external_id) DO UPDATE SET "
                "  pipeline_id = EXCLUDED.pipeline_id, name = EXCLUDED.name, "
                "  sort_order = EXCLUDED.sort_order, kind = EXCLUDED.kind, fetched_at = NOW() "
                "RETURNING id"
            ),
            {
                "id": tenant_uuid,
                "ext": ext_id,
                "pid": pipeline_uuid,
                "name": raw_s.name or "",
                "sort": raw_s.sort_order,
                "kind": raw_s.kind,
            },
        )
        row = result.fetchone()
        if row and row[0]:
            ext_to_uuid[ext_id] = str(row[0])
    return ext_to_uuid


def _pull_users(sess, connector, access_token: str) -> dict[str, str]:
    """Тянет CRM-пользователей (менеджеров). Маппинг external_id → UUID."""
    ext_to_uuid: dict[str, str] = {}

    for raw_u in connector.fetch_users(access_token):
        ext_id = raw_u.crm_id
        if not ext_id:
            continue
        _upsert_raw(sess, "raw_users", ext_id, raw_u.raw_payload)

        email_hash = _hash_pii(_normalize_email(raw_u.email))

        tenant_uuid = _uuid()
        result = sess.execute(
            text(
                "INSERT INTO crm_users(id, external_id, full_name, email_hash, role, is_active, fetched_at) "
                "VALUES (CAST(:id AS UUID), :ext, :name, :eh, :role, :active, NOW()) "
                "ON CONFLICT (external_id) DO UPDATE SET "
                "  full_name = EXCLUDED.full_name, email_hash = EXCLUDED.email_hash, "
                "  role = EXCLUDED.role, is_active = EXCLUDED.is_active, fetched_at = NOW() "
                "RETURNING id"
            ),
            {
                "id": tenant_uuid,
                "ext": ext_id,
                "name": raw_u.name,
                "eh": email_hash,
                "role": raw_u.role,
                "active": bool(raw_u.is_active),
            },
        )
        row = result.fetchone()
        if row and row[0]:
            ext_to_uuid[ext_id] = str(row[0])
    return ext_to_uuid


def _pull_contacts(
    sess,
    connector,
    access_token: str,
    user_map: dict[str, str],
    limit: int | None,
) -> dict[str, str]:
    """Тянет контакты. Маппинг external_id → UUID. FK responsible_user_id → crm_users."""
    ext_to_uuid: dict[str, str] = {}

    for raw_c in connector.fetch_contacts(access_token, limit=limit):
        ext_id = raw_c.crm_id
        if not ext_id:
            continue
        _upsert_raw(sess, "raw_contacts", ext_id, raw_c.raw_payload)

        phone_hash = _hash_pii(_normalize_phone(raw_c.phone))
        email_hash = _hash_pii(_normalize_email(raw_c.email))
        resp_uuid = user_map.get(raw_c.responsible_user_id) if raw_c.responsible_user_id else None

        tenant_uuid = _uuid()
        result = sess.execute(
            text(
                "INSERT INTO contacts(id, external_id, full_name, phone_primary_hash, "
                "                     email_primary_hash, responsible_user_id, "
                "                     created_at_external, fetched_at) "
                "VALUES (CAST(:id AS UUID), :ext, :name, :ph, :eh, "
                "        CAST(NULLIF(:uid, '') AS UUID), :ca, NOW()) "
                "ON CONFLICT (external_id) DO UPDATE SET "
                "  full_name = EXCLUDED.full_name, "
                "  phone_primary_hash = EXCLUDED.phone_primary_hash, "
                "  email_primary_hash = EXCLUDED.email_primary_hash, "
                "  responsible_user_id = EXCLUDED.responsible_user_id, "
                "  created_at_external = EXCLUDED.created_at_external, fetched_at = NOW() "
                "RETURNING id"
            ),
            {
                "id": tenant_uuid,
                "ext": ext_id,
                "name": raw_c.name,
                "ph": phone_hash,
                "eh": email_hash,
                "uid": resp_uuid or "",
                "ca": raw_c.created_at,
            },
        )
        row = result.fetchone()
        if row and row[0]:
            ext_to_uuid[ext_id] = str(row[0])
    return ext_to_uuid


def _pull_deals(
    sess,
    connector,
    access_token: str,
    *,
    pipeline_map: dict[str, str],
    stage_map: dict[str, str],
    user_map: dict[str, str],
    contact_map: dict[str, str],
    since: datetime | None,
    limit: int | None,
) -> int:
    """
    Тянет сделки. Возвращает количество обработанных сделок.
    FK: pipeline_id, stage_id, responsible_user_id, contact_id.
    Компании пока не поднимаем (Phase 2B) → company_id=NULL.
    """
    processed = 0
    for raw_d in connector.fetch_deals(access_token, since=since, limit=limit):
        ext_id = raw_d.crm_id
        if not ext_id:
            continue
        _upsert_raw(sess, "raw_deals", ext_id, raw_d.raw_payload)

        pipeline_uuid = pipeline_map.get(raw_d.pipeline_id) if raw_d.pipeline_id else None
        stage_uuid = stage_map.get(raw_d.stage_id) if raw_d.stage_id else None
        resp_uuid = user_map.get(raw_d.responsible_user_id) if raw_d.responsible_user_id else None
        contact_uuid = contact_map.get(raw_d.contact_id) if raw_d.contact_id else None

        price_cents: int | None = None
        if raw_d.price is not None:
            # amoCRM хранит цену в рублях (float) → умножаем на 100.
            price_cents = int(round(float(raw_d.price) * 100))

        sess.execute(
            text(
                "INSERT INTO deals(id, external_id, name, pipeline_id, stage_id, status, "
                "                  responsible_user_id, contact_id, company_id, price_cents, currency, "
                "                  created_at_external, updated_at_external, closed_at_external, fetched_at) "
                "VALUES (CAST(:id AS UUID), :ext, :name, "
                "        CAST(NULLIF(:pid, '') AS UUID), "
                "        CAST(NULLIF(:sid, '') AS UUID), :status, "
                "        CAST(NULLIF(:uid, '') AS UUID), "
                "        CAST(NULLIF(:cid, '') AS UUID), "
                "        NULL, :price, :cur, :ca, :ua, :cla, NOW()) "
                "ON CONFLICT (external_id) DO UPDATE SET "
                "  name = EXCLUDED.name, pipeline_id = EXCLUDED.pipeline_id, "
                "  stage_id = EXCLUDED.stage_id, status = EXCLUDED.status, "
                "  responsible_user_id = EXCLUDED.responsible_user_id, "
                "  contact_id = EXCLUDED.contact_id, price_cents = EXCLUDED.price_cents, "
                "  currency = EXCLUDED.currency, "
                "  created_at_external = EXCLUDED.created_at_external, "
                "  updated_at_external = EXCLUDED.updated_at_external, "
                "  closed_at_external = EXCLUDED.closed_at_external, fetched_at = NOW()"
            ),
            {
                "id": _uuid(),
                "ext": ext_id,
                "name": raw_d.name,
                "pid": pipeline_uuid or "",
                "sid": stage_uuid or "",
                "status": raw_d.status,
                "uid": resp_uuid or "",
                "cid": contact_uuid or "",
                "price": price_cents,
                "cur": raw_d.currency,
                "ca": raw_d.created_at,
                "ua": raw_d.updated_at,
                "cla": raw_d.closed_at,
            },
        )
        processed += 1
    return processed


# ---------------------------------------------------------------------------
# Public job entrypoint
# ---------------------------------------------------------------------------

def pull_amocrm_core(
    connection_id: str,
    *,
    first_pull: bool = False,
    since_iso: str | None = None,
    deals_limit: int | None = None,
    contacts_limit: int | None = None,
    job_row_id: str | None = None,
) -> dict[str, Any]:
    """
    Phase 2A pull: pipelines + stages + users + contacts + deals.

    Args:
        connection_id: UUID из ``public.crm_connections``.
        first_pull: True только после OAuth-callback'а. В MOCK-режиме
            делегирует ``trial_export``, чтобы FE увидел данные.
        since_iso: ISO-8601 UTC timestamp. ``None`` → полный дамп.
        deals_limit / contacts_limit: верхние отсечки (для trial/audit).
        job_row_id: UUID public.jobs, проставляется enqueue-логикой.

    После успешного pull'а enqueue-ит ``run_audit_report`` через RQ.

    Returns:
        ``{connection_id, counts: {...}, audit_job_enqueued: bool}``.
    """
    mark_job_running(job_row_id)
    try:
        # ---- MOCK path -------------------------------------------------------
        if MOCK_CRM_MODE:
            from .export import trial_export
            export_result = trial_export(connection_id=connection_id, job_row_id=None)
            audit_enqueued = _enqueue_audit(connection_id)
            with sync_session() as sess:
                sess.execute(
                    text(
                        "UPDATE crm_connections SET last_sync_at=NOW(), updated_at=NOW() "
                        "WHERE id=CAST(:cid AS UUID)"
                    ),
                    {"cid": connection_id},
                )
            result = {
                "connection_id": connection_id,
                "mock": True,
                "counts": {
                    "pipelines": export_result.get("pipelines_created", 0),
                    "stages": export_result.get("stages_created", 0),
                    "users": export_result.get("crm_users_created", 0),
                    "contacts": export_result.get("contacts_created", 0),
                    "deals": export_result.get("deals_created", 0),
                },
                "audit_job_enqueued": audit_enqueued,
            }
            mark_job_succeeded(job_row_id, result)
            return result

        # ---- REAL path -------------------------------------------------------
        conn_info = _fetch_connection_row(connection_id)
        if conn_info["provider"] != "amocrm":
            raise NotImplementedError(
                f"pull_amocrm_core: провайдер '{conn_info['provider']}' не поддержан (Phase 2A)."
            )
        schema = conn_info.get("tenant_schema")
        if not schema:
            # Ленивая инициализация: bootstrap_tenant_schema должен был отработать
            # до enqueue pull'а, но подстрахуемся.
            from .crm import bootstrap_tenant_schema
            bootstrap_tenant_schema(connection_id=connection_id, job_row_id=None)
            conn_info = _fetch_connection_row(connection_id)
            schema = conn_info.get("tenant_schema")
        if not schema:
            raise RuntimeError(f"tenant_schema не создана для {connection_id}")

        subdomain = _amocrm_subdomain(conn_info.get("external_domain"))
        if not subdomain:
            raise RuntimeError(
                f"external_domain='{conn_info.get('external_domain')}' невалиден — "
                "невозможно определить subdomain amoCRM"
            )

        access_token = _ensure_fresh_access_token(conn_info, connection_id)

        from crm_connectors.amocrm import AmoCrmConnector  # type: ignore

        # Task #52.3F (Bug F): OAuth-credentials теперь резолвятся по
        # ``crm_connections.amocrm_auth_mode``. Для ``external_button`` —
        # per-installation из БД (#44.6), для ``static_client`` / legacy —
        # env AMOCRM_CLIENT_ID/SECRET. Fallback на env для external_button
        # запрещён (см. load_amocrm_oauth_credentials): это предотвращает
        # утечку глобальных creds в чужой аккаунт.
        client_id, client_secret = load_amocrm_oauth_credentials(
            conn_info, connection_id=connection_id
        )

        connector = AmoCrmConnector(
            client_id=client_id,
            client_secret=client_secret,
            subdomain=subdomain,
        )

        since: datetime | None = None
        if since_iso:
            try:
                since = datetime.fromisoformat(since_iso.replace("Z", "+00:00"))
            except ValueError:
                logger.warning(
                    "crm_pull_bad_since_iso",
                    extra={"connection_id": connection_id, "since_iso": since_iso},
                )
                since = None

        q_schema = f'"{schema}"'
        counts: dict[str, int] = {}

        with sync_session() as sess:
            sess.execute(text(f"SET LOCAL search_path = {q_schema}, public"))

            logger.info(
                "crm_pull_started",
                extra={"connection_id": connection_id, "schema": schema, "first_pull": first_pull},
            )

            pipeline_map = _pull_pipelines(sess, connector, access_token)
            counts["pipelines"] = len(pipeline_map)

            stage_map = _pull_stages(sess, connector, access_token, pipeline_map)
            counts["stages"] = len(stage_map)

            user_map = _pull_users(sess, connector, access_token)
            counts["users"] = len(user_map)

            contact_map = _pull_contacts(
                sess, connector, access_token, user_map, contacts_limit
            )
            counts["contacts"] = len(contact_map)

            deals_count = _pull_deals(
                sess,
                connector,
                access_token,
                pipeline_map=pipeline_map,
                stage_map=stage_map,
                user_map=user_map,
                contact_map=contact_map,
                since=since,
                limit=deals_limit,
            )
            counts["deals"] = deals_count

        # Обновляем метаданные CrmConnection.
        import json
        with sync_session() as sess:
            sess.execute(
                text(
                    "UPDATE crm_connections SET "
                    "  last_sync_at = NOW(), "
                    "  updated_at = NOW(), "
                    "  metadata_json = COALESCE(metadata_json, '{}'::jsonb) "
                    "    || CAST(:patch AS JSONB) "
                    "WHERE id = CAST(:cid AS UUID)"
                ),
                {
                    "cid": connection_id,
                    "patch": json.dumps(
                        {
                            "last_pull_counts": counts,
                            "last_pull_at": datetime.now(tz=timezone.utc).isoformat(),
                        },
                        ensure_ascii=False,
                    ),
                },
            )

        audit_enqueued = _enqueue_audit(connection_id)

        logger.info(
            "crm_pull_done",
            extra={
                "connection_id": connection_id,
                "schema": schema,
                "counts": counts,
            },
        )

        result = {
            "connection_id": connection_id,
            "mock": False,
            "first_pull": first_pull,
            "tenant_schema": schema,
            "counts": counts,
            "audit_job_enqueued": audit_enqueued,
        }
        mark_job_succeeded(job_row_id, result)
        return result
    except Exception as exc:
        mark_job_failed(job_row_id, f"pull_amocrm_core: {exc}")
        raise


# ---------------------------------------------------------------------------
# Audit enqueue
# ---------------------------------------------------------------------------

def _enqueue_audit(connection_id: str) -> bool:
    """
    Enqueue ``run_audit_report`` после pull'а. При ошибке подключения к Redis
    возвращаем False и логируем — основной pull не валим.
    """
    try:
        from rq import Queue
        from redis import Redis
    except ImportError:
        logger.warning("crm_pull_rq_missing")
        return False

    try:
        redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        # run_audit_report живёт в очереди "audit" (см. apps/api/app/core/jobs.py
        # JOB_KIND_TO_QUEUE). Ставить в "crm" — worker просто никогда не заберёт.
        queue = Queue("audit", connection=Redis.from_url(redis_url))
        queue.enqueue("worker.jobs.audit.run_audit_report", connection_id)
        return True
    except Exception as exc:  # pragma: no cover — инфраструктурная ошибка
        logger.warning(
            "crm_pull_audit_enqueue_failed",
            extra={"connection_id": connection_id, "error": str(exc)[:200]},
        )
        return False


__all__ = [
    "pull_amocrm_core",
]
