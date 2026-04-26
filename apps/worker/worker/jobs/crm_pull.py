"""
CRM pull jobs (Phase 2A step 5).

Основной entry-point: ``pull_amocrm_core(connection_id, first_pull=False)``.

Что делает:

1. Читает ``crm_connections`` (access_token_encrypted, refresh_token_encrypted,
   token_expires_at, tenant_schema, external_domain).
2. При необходимости рефрешит access_token (inline вызов ``refresh_token``),
   если до экспирации осталось ≤ 120s.
3. Инстанцирует ``AmoCrmConnector(client_id, client_secret, subdomain)``.
4. Качает ядро в строгом порядке (зависимости FK):
   pipelines → stages → users → companies → contacts → deals.
5. Каждая сущность UPSERT'ится в raw_* + нормализованную таблицу
   внутри tenant-schema (search_path trick — как в ``trial_export``).
6. Ведёт in-memory маппинг ``external_id → tenant UUID`` для разрешения FK
   (stage→pipeline, deal→contact/company/user/pipeline/stage, contact→user).
7. Обновляет ``CrmConnection.last_sync_at`` и кладёт сводку в колонку
   ``metadata`` (ORM-атрибут ``CrmConnection.metadata_json`` через
   ``Column("metadata", JSONB, ...)``; в raw SQL — реальное имя колонки).
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
import json
import logging
import os
import re
import uuid as uuid_mod
from datetime import datetime, time, timedelta, timezone
from typing import Any, Callable, Iterable

from sqlalchemy import text

from ..lib.amocrm_creds import load_amocrm_oauth_credentials
from ..lib.crypto import decrypt_token
from ..lib.db import sync_session
from ._common import (
    charge_token_reservation_for_job,
    create_job_notification,
    mark_job_failed,
    mark_job_running,
    mark_job_succeeded,
    release_token_reservation_for_job,
    update_job_progress,
)

logger = logging.getLogger("code9.worker.crm_pull")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


MOCK_CRM_MODE = os.getenv("MOCK_CRM_MODE", "true").lower() == "true"
AMOCRM_GLOBAL_NOTES_ENABLED = os.getenv("AMOCRM_GLOBAL_NOTES_ENABLED", "false").lower() == "true"
AMOCRM_TIMELINE_MESSAGES_ENABLED = (
    os.getenv("AMOCRM_TIMELINE_MESSAGES_ENABLED", "false").lower() == "true"
)
AMOCRM_FULL_EXPORT_EVENTS_ENABLED = (
    os.getenv("AMOCRM_FULL_EXPORT_EVENTS_ENABLED", "false").lower() == "true"
)
AMOCRM_MESSAGES_IMPORT_LIMIT_DEFAULT = _env_int("AMOCRM_MESSAGES_IMPORT_LIMIT", 2000)
AMOCRM_MESSAGES_ENTITY_LIMIT_DEFAULT = _env_int("AMOCRM_MESSAGES_ENTITY_LIMIT", 0)
AMOCRM_EVENTS_IMPORT_LIMIT_DEFAULT = _env_int("AMOCRM_EVENTS_IMPORT_LIMIT", 50000)

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
                "       amocrm_client_secret_encrypted, metadata "
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
        "metadata": row[10] or {},
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


def _parse_export_date_start(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        if "T" not in value:
            return datetime.combine(
                datetime.fromisoformat(value).date(),
                time.min,
                tzinfo=timezone.utc,
            )
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _parse_export_date_end(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        if "T" not in value:
            return datetime.combine(
                datetime.fromisoformat(value).date(),
                time.max,
                tzinfo=timezone.utc,
            )
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _build_active_export_metadata(
    *,
    date_from_iso: str | None,
    date_to_iso: str | None,
    pipeline_ids: list[str] | None,
    counts: dict[str, int],
    messages_coverage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "mode": "real",
        "date_basis": "created_at",
        "date_from": date_from_iso,
        "date_to": date_to_iso,
        "pipeline_ids": [str(pid) for pid in (pipeline_ids or [])],
        "counts": counts,
        "completed_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    if messages_coverage:
        payload["messages_coverage"] = messages_coverage
    return payload


def _cleanup_trial_export_rows(sess, *, schema: str) -> None:
    """Remove only deterministic Code9 trial rows before a real export."""
    q_schema = f'"{schema}"'
    # Delete child tables first to satisfy FK constraints.
    statements = [
        (f"DELETE FROM {q_schema}.deals WHERE external_id LIKE 'ext-deal-%'", {}),
        (f"DELETE FROM {q_schema}.contacts WHERE external_id LIKE 'ext-contact-%'", {}),
        (f"DELETE FROM {q_schema}.companies WHERE external_id LIKE 'ext-company-%'", {}),
        (f"DELETE FROM {q_schema}.stages WHERE external_id LIKE 'ext-stage-%'", {}),
        (f"DELETE FROM {q_schema}.crm_users WHERE external_id LIKE 'ext-user-%'", {}),
        (f"DELETE FROM {q_schema}.pipelines WHERE external_id LIKE 'ext-pipe-%'", {}),
    ]
    for sql, params in statements:
        sess.execute(text(sql), params)


def _pipeline_filter_placeholders(
    pipeline_ids: list[str] | None,
    *,
    prefix: str,
) -> tuple[str, dict[str, str]]:
    placeholders: list[str] = []
    params: dict[str, str] = {}
    for idx, pipeline_id in enumerate(pipeline_ids or []):
        key = f"{prefix}_{idx}"
        placeholders.append(f":{key}")
        params[key] = str(pipeline_id)
    return ", ".join(placeholders), params


def _tenant_table_count(sess, *, schema: str, table: str) -> int:
    allowed = {
        "pipelines",
        "stages",
        "crm_users",
        "companies",
        "contacts",
        "deals",
        "tags",
        "products",
        "deal_products",
        "tasks",
        "notes",
        "calls",
        "chats",
        "messages",
        "raw_events",
        "deal_contacts",
        "deal_companies",
        "deal_stage_transitions",
        "deal_sources",
        "crm_custom_fields",
        "crm_custom_field_values",
    }
    if table not in allowed:
        raise ValueError(f"Unsupported tenant count table: {table}")
    q_schema = f'"{schema}"'
    value = sess.execute(text(f"SELECT COUNT(*) FROM {q_schema}.{table}")).scalar()
    return int(value or 0)


def _tenant_active_deals_count(
    sess,
    *,
    schema: str,
    created_from: datetime | None,
    created_to: datetime | None,
    pipeline_ids: list[str] | None,
) -> int:
    q_schema = f'"{schema}"'
    clauses: list[str] = []
    params: dict[str, Any] = {}
    if created_from:
        clauses.append("d.created_at_external >= :created_from")
        params["created_from"] = created_from
    if created_to:
        clauses.append("d.created_at_external <= :created_to")
        params["created_to"] = created_to
    if pipeline_ids:
        pipeline_placeholders, pipeline_params = _pipeline_filter_placeholders(
            pipeline_ids,
            prefix="active_pipeline",
        )
        clauses.append(f"p.external_id IN ({pipeline_placeholders})")
        params.update(pipeline_params)
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    value = sess.execute(
        text(
            f"SELECT COUNT(*) "
            f"FROM {q_schema}.deals d "
            f"LEFT JOIN {q_schema}.pipelines p ON p.id = d.pipeline_id "
            f"{where_sql}"
        ),
        params,
    ).scalar()
    return int(value or 0)


def _tenant_active_export_counts(
    sess,
    *,
    schema: str,
    created_from: datetime | None,
    created_to: datetime | None,
    pipeline_ids: list[str] | None,
) -> dict[str, int]:
    q_schema = f'"{schema}"'
    counts = {
        "pipelines": _tenant_table_count(sess, schema=schema, table="pipelines"),
        "stages": _tenant_table_count(sess, schema=schema, table="stages"),
        "users": _tenant_table_count(sess, schema=schema, table="crm_users"),
        "companies": _tenant_table_count(sess, schema=schema, table="companies"),
        "contacts": _tenant_table_count(sess, schema=schema, table="contacts"),
        "deals": _tenant_active_deals_count(
            sess,
            schema=schema,
            created_from=created_from,
            created_to=created_to,
            pipeline_ids=pipeline_ids,
        ),
        "tags": _tenant_table_count(sess, schema=schema, table="tags"),
        "products": _tenant_table_count(sess, schema=schema, table="products"),
        "deal_products": _tenant_table_count(sess, schema=schema, table="deal_products"),
        "tasks": _tenant_table_count(sess, schema=schema, table="tasks"),
        "notes": _tenant_table_count(sess, schema=schema, table="notes"),
        "calls": _tenant_table_count(sess, schema=schema, table="calls"),
        "chats": _tenant_table_count(sess, schema=schema, table="chats"),
        "messages": _tenant_table_count(sess, schema=schema, table="messages"),
        "events": _tenant_table_count(sess, schema=schema, table="raw_events"),
        "deal_contacts": _tenant_table_count(sess, schema=schema, table="deal_contacts"),
        "deal_companies": _tenant_table_count(sess, schema=schema, table="deal_companies"),
        "stage_transitions": _tenant_table_count(
            sess,
            schema=schema,
            table="deal_stage_transitions",
        ),
        "deal_sources": _tenant_table_count(sess, schema=schema, table="deal_sources"),
        "custom_fields": _tenant_table_count(sess, schema=schema, table="crm_custom_fields"),
        "custom_field_values": _tenant_table_count(
            sess,
            schema=schema,
            table="crm_custom_field_values",
        ),
    }
    if pipeline_ids:
        pipeline_placeholders, pipeline_params = _pipeline_filter_placeholders(
            pipeline_ids,
            prefix="selected_pipeline",
        )
        counts["pipelines"] = int(
            sess.execute(
                text(
                    f"SELECT COUNT(*) FROM {q_schema}.pipelines "
                    f"WHERE external_id IN ({pipeline_placeholders})"
                ),
                pipeline_params,
            ).scalar()
            or 0
        )
        counts["stages"] = int(
            sess.execute(
                text(
                    f"SELECT COUNT(*) "
                    f"FROM {q_schema}.stages s "
                    f"JOIN {q_schema}.pipelines p ON p.id = s.pipeline_id "
                    f"WHERE p.external_id IN ({pipeline_placeholders})"
                ),
                pipeline_params,
            ).scalar()
            or 0
        )
    return counts


# ---------------------------------------------------------------------------
# UPSERT helpers
# ---------------------------------------------------------------------------

def _upsert_raw(
    sess, schema: str, table: str, external_id: str, payload: dict[str, Any]
) -> None:
    """UPSERT в ``"<schema>".raw_<entity>``: (external_id UNIQUE) → refresh payload.

    Task #52.7: schema qualified explicitly — не полагаемся только на
    ``SET LOCAL search_path``. В проде наблюдалась потеря search_path
    между execute'ами (см. docstring ``trial_export``), INSERT падал с
    ``UndefinedTable``. Schema — строго валидированный идентификатор,
    инъекция исключена на уровне ``_validate_schema_name`` в
    ``apply_tenant_template``.
    """
    import json

    sess.execute(
        text(
            f'INSERT INTO "{schema}".{table}(id, external_id, payload, fetched_at) '
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


def _load_external_id_map(sess, *, schema: str, table: str) -> dict[str, str]:
    """Load tenant normalized row ids by external_id for FK resolution."""
    allowed = {
        "pipelines",
        "stages",
        "crm_users",
        "companies",
        "contacts",
        "deals",
        "tags",
        "products",
    }
    if table not in allowed:
        raise ValueError(f"Unsupported external_id map table: {table}")
    q_schema = f'"{schema}"'
    rows = sess.execute(text(f"SELECT external_id, id FROM {q_schema}.{table}")).fetchall()
    return {str(row[0]): str(row[1]) for row in rows if row[0] and row[1]}


def _load_selected_deal_rows(
    sess,
    *,
    schema: str,
    created_from: datetime | None,
    created_to: datetime | None,
    pipeline_ids: list[str] | None,
) -> list[tuple[str, str]]:
    """Return selected deals as (external_id, tenant_uuid) for message import."""
    q_schema = f'"{schema}"'
    clauses = ["d.external_id IS NOT NULL"]
    params: dict[str, Any] = {}
    if created_from:
        clauses.append("d.created_at_external >= :created_from")
        params["created_from"] = created_from
    if created_to:
        clauses.append("d.created_at_external <= :created_to")
        params["created_to"] = created_to
    if pipeline_ids:
        pipeline_placeholders, pipeline_params = _pipeline_filter_placeholders(
            pipeline_ids,
            prefix="message_pipeline",
        )
        clauses.append(f"p.external_id IN ({pipeline_placeholders})")
        params.update(pipeline_params)
    rows = sess.execute(
        text(
            f"SELECT d.external_id, d.id "
            f"FROM {q_schema}.deals d "
            f"LEFT JOIN {q_schema}.pipelines p ON p.id = d.pipeline_id "
            f"WHERE {' AND '.join(clauses)} "
            "ORDER BY d.created_at_external DESC NULLS LAST, d.external_id"
        ),
        params,
    ).fetchall()
    return [(str(row[0]), str(row[1])) for row in rows if row[0] and row[1]]


def _load_selected_contact_rows(
    sess,
    *,
    schema: str,
    created_from: datetime | None,
    created_to: datetime | None,
    pipeline_ids: list[str] | None,
) -> list[tuple[str, str]]:
    """Return contacts related to selected deals as (external_id, tenant_uuid)."""
    q_schema = f'"{schema}"'
    clauses = ["c.external_id IS NOT NULL"]
    params: dict[str, Any] = {}
    if created_from:
        clauses.append("d.created_at_external >= :created_from")
        params["created_from"] = created_from
    if created_to:
        clauses.append("d.created_at_external <= :created_to")
        params["created_to"] = created_to
    if pipeline_ids:
        pipeline_placeholders, pipeline_params = _pipeline_filter_placeholders(
            pipeline_ids,
            prefix="contact_scope_pipeline",
        )
        clauses.append(f"p.external_id IN ({pipeline_placeholders})")
        params.update(pipeline_params)
    rows = sess.execute(
        text(
            f"SELECT DISTINCT c.external_id, c.id, c.created_at_external "
            f"FROM {q_schema}.deals d "
            f"LEFT JOIN {q_schema}.pipelines p ON p.id = d.pipeline_id "
            f"LEFT JOIN {q_schema}.deal_contacts dc ON dc.deal_id = d.id "
            f"LEFT JOIN {q_schema}.contacts c ON c.id = COALESCE(dc.contact_id, d.contact_id) "
            f"WHERE {' AND '.join(clauses)} "
            "ORDER BY c.created_at_external DESC NULLS LAST, c.external_id"
        ),
        params,
    ).fetchall()
    return [(str(row[0]), str(row[1])) for row in rows if row[0] and row[1]]


def _catalog_element_external_id(element: dict[str, Any]) -> str | None:
    element_id = element.get("id")
    if element_id is None:
        return None
    catalog_id = element.get("catalog_id")
    if catalog_id is None:
        return str(element_id)
    return f"{catalog_id}:{element_id}"


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, default=str)


def _custom_field_text(values: Any) -> str | None:
    if not isinstance(values, list) or not values:
        return None
    parts: list[str] = []
    for item in values:
        if not isinstance(item, dict):
            continue
        value = item.get("value")
        if value is None:
            continue
        if isinstance(value, (dict, list)):
            parts.append(json.dumps(value, ensure_ascii=False, default=str))
        else:
            parts.append(str(value))
    text_value = ", ".join(part for part in parts if part.strip())
    return text_value or None


def _upsert_custom_field_def(
    sess,
    *,
    schema: str,
    entity_type: str,
    field_external_id: str,
    field_name: str | None,
    field_code: str | None,
    field_type: str | None,
    raw_metadata: dict[str, Any],
) -> str | None:
    q_schema = f'"{schema}"'
    result = sess.execute(
        text(
            f"INSERT INTO {q_schema}.crm_custom_fields("
            "id, entity_type, external_id, name, code, field_type, raw_metadata, fetched_at"
            ") VALUES (CAST(:id AS UUID), :entity_type, :external_id, :name, :code, "
            ":field_type, CAST(:raw_metadata AS JSONB), NOW()) "
            "ON CONFLICT (entity_type, external_id) DO UPDATE SET "
            "  name = COALESCE(EXCLUDED.name, crm_custom_fields.name), "
            "  code = COALESCE(EXCLUDED.code, crm_custom_fields.code), "
            "  field_type = COALESCE(EXCLUDED.field_type, crm_custom_fields.field_type), "
            "  raw_metadata = CASE WHEN EXCLUDED.raw_metadata = '{}'::jsonb "
            "    THEN crm_custom_fields.raw_metadata ELSE EXCLUDED.raw_metadata END, "
            "  fetched_at = NOW() "
            "RETURNING id"
        ),
        {
            "id": _uuid(),
            "entity_type": entity_type,
            "external_id": field_external_id,
            "name": field_name,
            "code": field_code,
            "field_type": field_type,
            "raw_metadata": _json_dumps(raw_metadata),
        },
    )
    row = result.fetchone()
    return str(row[0]) if row and row[0] else None


def _sync_custom_field_values(
    sess,
    *,
    schema: str,
    entity_type: str,
    entity_external_id: str,
    payload: dict[str, Any],
) -> int:
    values = payload.get("custom_fields_values") if isinstance(payload, dict) else None
    if not isinstance(values, list):
        return 0
    q_schema = f'"{schema}"'
    processed = 0
    for field in values:
        if not isinstance(field, dict):
            continue
        field_id = field.get("field_id") or field.get("id")
        if field_id is None:
            continue
        field_external_id = str(field_id)
        field_name = field.get("field_name") or field.get("name")
        field_code = field.get("field_code") or field.get("code")
        field_type = field.get("field_type") or field.get("type")
        custom_field_uuid = _upsert_custom_field_def(
            sess,
            schema=schema,
            entity_type=entity_type,
            field_external_id=field_external_id,
            field_name=str(field_name) if field_name is not None else None,
            field_code=str(field_code) if field_code is not None else None,
            field_type=str(field_type) if field_type is not None else None,
            raw_metadata=field,
        )
        sess.execute(
            text(
                f"INSERT INTO {q_schema}.crm_custom_field_values("
                "id, entity_type, entity_external_id, custom_field_id, field_external_id, "
                "field_name, value_text, value_json, fetched_at"
                ") VALUES (CAST(:id AS UUID), :entity_type, :entity_external_id, "
                "CAST(NULLIF(:custom_field_id, '') AS UUID), :field_external_id, "
                ":field_name, :value_text, CAST(:value_json AS JSONB), NOW()) "
                "ON CONFLICT (entity_type, entity_external_id, field_external_id) DO UPDATE SET "
                "  custom_field_id = EXCLUDED.custom_field_id, "
                "  field_name = EXCLUDED.field_name, "
                "  value_text = EXCLUDED.value_text, "
                "  value_json = EXCLUDED.value_json, fetched_at = NOW()"
            ),
            {
                "id": _uuid(),
                "entity_type": entity_type,
                "entity_external_id": entity_external_id,
                "custom_field_id": custom_field_uuid or "",
                "field_external_id": field_external_id,
                "field_name": str(field_name) if field_name is not None else None,
                "value_text": _custom_field_text(field.get("values")),
                "value_json": _json_dumps(field.get("values") if field.get("values") is not None else []),
            },
        )
        processed += 1
    return processed


def _embedded_items(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    embedded = payload.get("_embedded") if isinstance(payload, dict) else None
    items = embedded.get(key) if isinstance(embedded, dict) else None
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def _sync_deal_products(
    sess,
    *,
    schema: str,
    deal_uuid: str,
    catalog_elements: list[Any],
    product_map: dict[str, str] | None,
) -> int:
    """Sync amoCRM ``_embedded.catalog_elements`` for a normalized deal."""
    q_schema = f'"{schema}"'
    seen_external_ids: list[str] = []
    processed = 0
    for element in catalog_elements:
        if not isinstance(element, dict):
            continue
        ext_id = _catalog_element_external_id(element)
        if not ext_id:
            continue
        seen_external_ids.append(ext_id)
        metadata = element.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        catalog_id = element.get("catalog_id")
        quantity = _float_or_none(element.get("quantity") or metadata.get("quantity"))
        price = _float_or_none(
            element.get("price")
            or element.get("price_value")
            or metadata.get("price")
            or metadata.get("price_value")
        )
        price_cents = int(round(price * 100)) if price is not None else None
        price_id = element.get("price_id") or metadata.get("price_id")
        product_uuid = (product_map or {}).get(ext_id)
        sess.execute(
            text(
                f"INSERT INTO {q_schema}.deal_products("
                "deal_id, product_id, external_id, catalog_id, quantity, "
                "price_cents, price_id, raw_metadata, fetched_at"
                ") VALUES ("
                "CAST(:deal_id AS UUID), CAST(NULLIF(:product_id, '') AS UUID), "
                ":ext, :catalog_id, :quantity, :price, :price_id, "
                "CAST(:raw_metadata AS JSONB), NOW()"
                ") ON CONFLICT (deal_id, external_id) DO UPDATE SET "
                "  product_id = COALESCE(EXCLUDED.product_id, deal_products.product_id), "
                "  catalog_id = EXCLUDED.catalog_id, quantity = EXCLUDED.quantity, "
                "  price_cents = EXCLUDED.price_cents, price_id = EXCLUDED.price_id, "
                "  raw_metadata = EXCLUDED.raw_metadata, fetched_at = NOW()"
            ),
            {
                "deal_id": deal_uuid,
                "product_id": product_uuid or "",
                "ext": ext_id,
                "catalog_id": str(catalog_id) if catalog_id is not None else None,
                "quantity": quantity,
                "price": price_cents,
                "price_id": str(price_id) if price_id is not None else None,
                "raw_metadata": json.dumps(element, ensure_ascii=False, default=str),
            },
        )
        processed += 1
    if seen_external_ids:
        params = {"deal_id": deal_uuid}
        placeholders: list[str] = []
        for idx, ext_id in enumerate(seen_external_ids):
            key = f"linked_product_{idx}"
            placeholders.append(f":{key}")
            params[key] = ext_id
        sess.execute(
            text(
                f"DELETE FROM {q_schema}.deal_products "
                f"WHERE deal_id = CAST(:deal_id AS UUID) "
                f"AND external_id NOT IN ({', '.join(placeholders)})"
            ),
            params,
        )
    else:
        sess.execute(
            text(
                f"DELETE FROM {q_schema}.deal_products "
                "WHERE deal_id = CAST(:deal_id AS UUID)"
            ),
            {"deal_id": deal_uuid},
        )
    return processed


def _link_deal_products_to_products(sess, *, schema: str) -> int:
    """Backfill product_id after catalog products have been imported."""
    q_schema = f'"{schema}"'
    value = sess.execute(
        text(
            f"UPDATE {q_schema}.deal_products dp "
            f"SET product_id = p.id, fetched_at = NOW() "
            f"FROM {q_schema}.products p "
            "WHERE dp.external_id = p.external_id "
            "AND (dp.product_id IS NULL OR dp.product_id <> p.id)"
        )
    ).rowcount
    return int(value or 0)


def _sync_deal_contacts(
    sess,
    *,
    schema: str,
    deal_uuid: str,
    contact_map: dict[str, str],
    contacts: list[dict[str, Any]],
) -> int:
    q_schema = f'"{schema}"'
    sess.execute(
        text(f"DELETE FROM {q_schema}.deal_contacts WHERE deal_id = CAST(:deal_id AS UUID)"),
        {"deal_id": deal_uuid},
    )
    seen: set[str] = set()
    for idx, contact in enumerate(contacts):
        contact_id = contact.get("id")
        contact_uuid = contact_map.get(str(contact_id)) if contact_id is not None else None
        if not contact_uuid:
            continue
        seen.add(contact_uuid)
        sess.execute(
            text(
                f"INSERT INTO {q_schema}.deal_contacts("
                "deal_id, contact_id, is_primary, raw_metadata, fetched_at"
                ") VALUES (CAST(:deal_id AS UUID), CAST(:contact_id AS UUID), "
                ":is_primary, CAST(:raw_metadata AS JSONB), NOW()) "
                "ON CONFLICT (deal_id, contact_id) DO UPDATE SET "
                "  is_primary = EXCLUDED.is_primary, "
                "  raw_metadata = EXCLUDED.raw_metadata, fetched_at = NOW()"
            ),
            {
                "deal_id": deal_uuid,
                "contact_id": contact_uuid,
                "is_primary": idx == 0,
                "raw_metadata": _json_dumps(contact),
            },
        )
    return len(seen)


def _sync_deal_companies(
    sess,
    *,
    schema: str,
    deal_uuid: str,
    company_map: dict[str, str],
    companies: list[dict[str, Any]],
) -> int:
    q_schema = f'"{schema}"'
    sess.execute(
        text(f"DELETE FROM {q_schema}.deal_companies WHERE deal_id = CAST(:deal_id AS UUID)"),
        {"deal_id": deal_uuid},
    )
    processed = 0
    for idx, company in enumerate(companies):
        company_id = company.get("id")
        company_uuid = company_map.get(str(company_id)) if company_id is not None else None
        if not company_uuid:
            continue
        sess.execute(
            text(
                f"INSERT INTO {q_schema}.deal_companies("
                "deal_id, company_id, is_primary, raw_metadata, fetched_at"
                ") VALUES (CAST(:deal_id AS UUID), CAST(:company_id AS UUID), "
                ":is_primary, CAST(:raw_metadata AS JSONB), NOW()) "
                "ON CONFLICT (deal_id, company_id) DO UPDATE SET "
                "  is_primary = EXCLUDED.is_primary, "
                "  raw_metadata = EXCLUDED.raw_metadata, fetched_at = NOW()"
            ),
            {
                "deal_id": deal_uuid,
                "company_id": company_uuid,
                "is_primary": idx == 0,
                "raw_metadata": _json_dumps(company),
            },
        )
        processed += 1
    return processed


def _sync_deal_source(
    sess,
    *,
    schema: str,
    deal_uuid: str,
    payload: dict[str, Any],
) -> int:
    embedded = payload.get("_embedded") if isinstance(payload, dict) else None
    source = embedded.get("source") if isinstance(embedded, dict) else None
    custom_values = payload.get("custom_fields_values") if isinstance(payload, dict) else None
    source_name = None
    source_type = None
    raw_metadata: dict[str, Any] = {}
    if isinstance(source, dict):
        source_name = source.get("name") or source.get("external_id")
        source_type = source.get("type") or source.get("service")
        raw_metadata["source"] = source

    def field_hint(*names: str) -> str | None:
        if not isinstance(custom_values, list):
            return None
        lowered = tuple(name.lower() for name in names)
        for field in custom_values:
            if not isinstance(field, dict):
                continue
            field_name = str(field.get("field_name") or field.get("name") or "").lower()
            field_code = str(field.get("field_code") or field.get("code") or "").lower()
            if not any(name in field_name or name in field_code for name in lowered):
                continue
            value = _custom_field_text(field.get("values"))
            if value:
                return value
        return None

    utm_source = field_hint("utm_source", "utm source")
    utm_medium = field_hint("utm_medium", "utm medium")
    utm_campaign = field_hint("utm_campaign", "utm campaign")
    utm_content = field_hint("utm_content", "utm content")
    utm_term = field_hint("utm_term", "utm term")

    if not any([source_name, source_type, utm_source, utm_medium, utm_campaign, utm_content, utm_term]):
        return 0
    q_schema = f'"{schema}"'
    sess.execute(
        text(
            f"INSERT INTO {q_schema}.deal_sources("
            "deal_id, source_name, source_type, utm_source, utm_medium, utm_campaign, "
            "utm_content, utm_term, raw_metadata, fetched_at"
            ") VALUES (CAST(:deal_id AS UUID), :source_name, :source_type, :utm_source, "
            ":utm_medium, :utm_campaign, :utm_content, :utm_term, "
            "CAST(:raw_metadata AS JSONB), NOW()) "
            "ON CONFLICT (deal_id) DO UPDATE SET "
            "  source_name = EXCLUDED.source_name, source_type = EXCLUDED.source_type, "
            "  utm_source = EXCLUDED.utm_source, utm_medium = EXCLUDED.utm_medium, "
            "  utm_campaign = EXCLUDED.utm_campaign, utm_content = EXCLUDED.utm_content, "
            "  utm_term = EXCLUDED.utm_term, raw_metadata = EXCLUDED.raw_metadata, "
            "  fetched_at = NOW()"
        ),
        {
            "deal_id": deal_uuid,
            "source_name": str(source_name) if source_name is not None else None,
            "source_type": str(source_type) if source_type is not None else None,
            "utm_source": utm_source,
            "utm_medium": utm_medium,
            "utm_campaign": utm_campaign,
            "utm_content": utm_content,
            "utm_term": utm_term,
            "raw_metadata": _json_dumps(raw_metadata),
        },
    )
    return 1


def _report_stage_items(
    progress: Callable[[int], None] | None,
    processed: int,
    *,
    every: int = 250,
) -> None:
    """Throttle DB writes while still giving the UI live row counters."""
    if progress is None or processed <= 0:
        return
    if processed % every == 0:
        progress(processed)


# ---------------------------------------------------------------------------
# Pull stages
# ---------------------------------------------------------------------------

def _pull_pipelines(
    sess, connector, access_token: str, *, schema: str
) -> dict[str, str]:
    """
    Тянет воронки. Возвращает маппинг external_id → tenant UUID.
    Используется downstream для stage.pipeline_id и deal.pipeline_id.
    """
    ext_to_uuid: dict[str, str] = {}
    q_schema = f'"{schema}"'

    for raw_p in connector.fetch_pipelines(access_token):
        ext_id = raw_p.crm_id
        if not ext_id:
            continue
        _upsert_raw(sess, schema, "raw_pipelines", ext_id, raw_p.raw_payload)

        # UPSERT normalized. ON CONFLICT возвращает id — используем RETURNING.
        tenant_uuid = _uuid()
        result = sess.execute(
            text(
                f"INSERT INTO {q_schema}.pipelines(id, external_id, name, is_default, fetched_at) "
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
    sess,
    connector,
    access_token: str,
    pipeline_map: dict[str, str],
    *,
    schema: str,
) -> dict[str, str]:
    """Тянет этапы всех воронок. Возвращает маппинг external_id → tenant UUID."""
    ext_to_uuid: dict[str, str] = {}
    q_schema = f'"{schema}"'

    for raw_s in connector.fetch_stages(access_token):
        ext_id = raw_s.crm_id
        if not ext_id:
            continue
        pipeline_uuid = pipeline_map.get(raw_s.pipeline_id)
        if not pipeline_uuid:
            # amoCRM не должен слать статус без pipeline, но на всякий пропустим.
            continue

        _upsert_raw(sess, schema, "raw_stages", ext_id, raw_s.raw_payload)

        tenant_uuid = _uuid()
        result = sess.execute(
            text(
                f"INSERT INTO {q_schema}.stages(id, external_id, pipeline_id, name, sort_order, kind, fetched_at) "
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


def _pull_users(
    sess, connector, access_token: str, *, schema: str
) -> dict[str, str]:
    """Тянет CRM-пользователей (менеджеров). Маппинг external_id → UUID."""
    ext_to_uuid: dict[str, str] = {}
    q_schema = f'"{schema}"'

    for raw_u in connector.fetch_users(access_token):
        ext_id = raw_u.crm_id
        if not ext_id:
            continue
        _upsert_raw(sess, schema, "raw_users", ext_id, raw_u.raw_payload)

        email_hash = _hash_pii(_normalize_email(raw_u.email))

        tenant_uuid = _uuid()
        result = sess.execute(
            text(
                f"INSERT INTO {q_schema}.crm_users(id, external_id, full_name, email_hash, role, is_active, fetched_at) "
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


def _pull_companies(
    sess,
    connector,
    access_token: str,
    user_map: dict[str, str],
    since: datetime | None,
    *,
    schema: str,
    progress: Callable[[int], None] | None = None,
) -> dict[str, str]:
    """Тянет компании. Маппинг external_id → UUID. FK responsible_user_id → crm_users."""
    ext_to_uuid: dict[str, str] = {}
    q_schema = f'"{schema}"'

    processed = 0
    for raw_c in connector.fetch_companies(access_token, since=since):
        ext_id = raw_c.crm_id
        if not ext_id:
            continue
        _upsert_raw(sess, schema, "raw_companies", ext_id, raw_c.raw_payload)

        inn_hash = _hash_pii(raw_c.inn.strip()) if raw_c.inn else None
        resp_uuid = user_map.get(raw_c.responsible_user_id) if raw_c.responsible_user_id else None

        tenant_uuid = _uuid()
        result = sess.execute(
            text(
                f"INSERT INTO {q_schema}.companies(id, external_id, name, inn_hash, "
                "                     created_at_external, fetched_at) "
                "VALUES (CAST(:id AS UUID), :ext, :name, :inn, :ca, NOW()) "
                "ON CONFLICT (external_id) DO UPDATE SET "
                "  name = EXCLUDED.name, "
                "  inn_hash = EXCLUDED.inn_hash, "
                "  created_at_external = EXCLUDED.created_at_external, fetched_at = NOW() "
                "RETURNING id"
            ),
            {
                "id": tenant_uuid,
                "ext": ext_id,
                "name": raw_c.name,
                "inn": inn_hash,
                "ca": raw_c.created_at,
            },
        )
        # Tenant schema currently has no responsible_user_id/phone/website columns
        # for companies; those fields stay in raw_companies.payload.
        _ = resp_uuid
        row = result.fetchone()
        if row and row[0]:
            ext_to_uuid[ext_id] = str(row[0])
        _sync_custom_field_values(
            sess,
            schema=schema,
            entity_type="company",
            entity_external_id=ext_id,
            payload=raw_c.raw_payload,
        )
        processed += 1
        _report_stage_items(progress, processed)
    if processed:
        _report_stage_items(progress, processed, every=1)
    return ext_to_uuid


def _pull_contacts(
    sess,
    connector,
    access_token: str,
    user_map: dict[str, str],
    since: datetime | None,
    limit: int | None,
    *,
    schema: str,
    progress: Callable[[int], None] | None = None,
) -> dict[str, str]:
    """Тянет контакты. Маппинг external_id → UUID. FK responsible_user_id → crm_users."""
    if limit == 0:
        return {}
    ext_to_uuid: dict[str, str] = {}
    q_schema = f'"{schema}"'

    processed = 0
    for raw_c in connector.fetch_contacts(access_token, since=since, limit=limit):
        ext_id = raw_c.crm_id
        if not ext_id:
            continue
        _upsert_raw(sess, schema, "raw_contacts", ext_id, raw_c.raw_payload)

        phone_hash = _hash_pii(_normalize_phone(raw_c.phone))
        email_hash = _hash_pii(_normalize_email(raw_c.email))
        resp_uuid = user_map.get(raw_c.responsible_user_id) if raw_c.responsible_user_id else None

        tenant_uuid = _uuid()
        result = sess.execute(
            text(
                f"INSERT INTO {q_schema}.contacts(id, external_id, full_name, phone_primary_hash, "
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
        _sync_custom_field_values(
            sess,
            schema=schema,
            entity_type="contact",
            entity_external_id=ext_id,
            payload=raw_c.raw_payload,
        )
        processed += 1
        _report_stage_items(progress, processed)
    if processed:
        _report_stage_items(progress, processed, every=1)
    return ext_to_uuid


def _pull_deals(
    sess,
    connector,
    access_token: str,
    *,
    pipeline_map: dict[str, str],
    stage_map: dict[str, str],
    user_map: dict[str, str],
    company_map: dict[str, str],
    contact_map: dict[str, str],
    since: datetime | None,
    created_from: datetime | None,
    created_to: datetime | None,
    pipeline_ids: list[str] | None,
    limit: int | None,
    schema: str,
    product_map: dict[str, str] | None = None,
    progress: Callable[[int], None] | None = None,
) -> int:
    """
    Тянет сделки. Возвращает количество обработанных сделок.
    FK: pipeline_id, stage_id, responsible_user_id, contact_id, company_id.
    """
    processed = 0
    q_schema = f'"{schema}"'

    def upsert_tag(tag: dict[str, Any]) -> str | None:
        name = str(tag.get("name") or "").strip()
        external = tag.get("id") or name
        if not name or external is None:
            return None
        ext_id = str(external)
        _upsert_raw(sess, schema, "raw_tags", ext_id, tag)
        result = sess.execute(
            text(
                f"INSERT INTO {q_schema}.tags(id, external_id, name, fetched_at) "
                "VALUES (CAST(:id AS UUID), :ext, :name, NOW()) "
                "ON CONFLICT (external_id) DO UPDATE SET "
                "  name = EXCLUDED.name, fetched_at = NOW() "
                "RETURNING id"
            ),
            {"id": _uuid(), "ext": ext_id, "name": name},
        )
        row = result.fetchone()
        return str(row[0]) if row and row[0] else None

    for raw_d in connector.fetch_deals(
        access_token,
        since=since,
        limit=limit,
        created_from=created_from,
        created_to=created_to,
        pipeline_ids=pipeline_ids,
    ):
        ext_id = raw_d.crm_id
        if not ext_id:
            continue
        _upsert_raw(sess, schema, "raw_deals", ext_id, raw_d.raw_payload)

        pipeline_uuid = pipeline_map.get(raw_d.pipeline_id) if raw_d.pipeline_id else None
        stage_uuid = stage_map.get(raw_d.stage_id) if raw_d.stage_id else None
        resp_uuid = user_map.get(raw_d.responsible_user_id) if raw_d.responsible_user_id else None
        contact_uuid = contact_map.get(raw_d.contact_id) if raw_d.contact_id else None
        company_uuid = company_map.get(raw_d.company_id) if raw_d.company_id else None

        price_cents: int | None = None
        if raw_d.price is not None:
            # amoCRM хранит цену в рублях (float) → умножаем на 100.
            price_cents = int(round(float(raw_d.price) * 100))

        result = sess.execute(
            text(
                f"INSERT INTO {q_schema}.deals(id, external_id, name, pipeline_id, stage_id, status, "
                "                  responsible_user_id, contact_id, company_id, price_cents, currency, "
                "                  created_at_external, updated_at_external, closed_at_external, fetched_at) "
                "VALUES (CAST(:id AS UUID), :ext, :name, "
                "        CAST(NULLIF(:pid, '') AS UUID), "
                "        CAST(NULLIF(:sid, '') AS UUID), :status, "
                "        CAST(NULLIF(:uid, '') AS UUID), "
                "        CAST(NULLIF(:cid, '') AS UUID), "
                "        CAST(NULLIF(:coid, '') AS UUID), "
                "        :price, :cur, :ca, :ua, :cla, NOW()) "
                "ON CONFLICT (external_id) DO UPDATE SET "
                "  name = EXCLUDED.name, pipeline_id = EXCLUDED.pipeline_id, "
                "  stage_id = EXCLUDED.stage_id, status = EXCLUDED.status, "
                "  responsible_user_id = EXCLUDED.responsible_user_id, "
                "  contact_id = EXCLUDED.contact_id, price_cents = EXCLUDED.price_cents, "
                "  company_id = EXCLUDED.company_id, currency = EXCLUDED.currency, "
                "  created_at_external = EXCLUDED.created_at_external, "
                "  updated_at_external = EXCLUDED.updated_at_external, "
                "  closed_at_external = EXCLUDED.closed_at_external, fetched_at = NOW() "
                "RETURNING id"
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
                "coid": company_uuid or "",
                "price": price_cents,
                "cur": raw_d.currency,
                "ca": raw_d.created_at,
                "ua": raw_d.updated_at,
                "cla": raw_d.closed_at,
            },
        )
        row = result.fetchone()
        deal_uuid = str(row[0]) if row and row[0] else None
        embedded = raw_d.raw_payload.get("_embedded") if isinstance(raw_d.raw_payload, dict) else {}
        tags = embedded.get("tags") if isinstance(embedded, dict) else []
        catalog_elements = (
            embedded.get("catalog_elements") if isinstance(embedded, dict) else []
        )
        if deal_uuid and isinstance(tags, list):
            for tag in tags:
                if not isinstance(tag, dict):
                    continue
                tag_uuid = upsert_tag(tag)
                if not tag_uuid:
                    continue
                sess.execute(
                    text(
                        f"INSERT INTO {q_schema}.deal_tags(deal_id, tag_id) "
                        "VALUES (CAST(:deal_id AS UUID), CAST(:tag_id AS UUID)) "
                        "ON CONFLICT DO NOTHING"
                    ),
                    {"deal_id": deal_uuid, "tag_id": tag_uuid},
                )
        if deal_uuid:
            _sync_deal_contacts(
                sess,
                schema=schema,
                deal_uuid=deal_uuid,
                contact_map=contact_map,
                contacts=_embedded_items(raw_d.raw_payload, "contacts"),
            )
            _sync_deal_companies(
                sess,
                schema=schema,
                deal_uuid=deal_uuid,
                company_map=company_map,
                companies=_embedded_items(raw_d.raw_payload, "companies"),
            )
            _sync_deal_source(
                sess,
                schema=schema,
                deal_uuid=deal_uuid,
                payload=raw_d.raw_payload,
            )
            _sync_custom_field_values(
                sess,
                schema=schema,
                entity_type="deal",
                entity_external_id=ext_id,
                payload=raw_d.raw_payload,
            )
        if deal_uuid and isinstance(catalog_elements, list):
            _sync_deal_products(
                sess,
                schema=schema,
                deal_uuid=deal_uuid,
                catalog_elements=catalog_elements,
                product_map=product_map,
            )
        processed += 1
        _report_stage_items(progress, processed)
    if processed:
        _report_stage_items(progress, processed, every=1)
    return processed


def _pull_custom_fields(
    sess,
    connector,
    access_token: str,
    *,
    schema: str,
    progress: Callable[[int], None] | None = None,
) -> int:
    """Pull amoCRM custom field definitions for analytics field mapping."""
    fetch_custom_fields = getattr(connector, "fetch_custom_fields", None)
    if not callable(fetch_custom_fields):
        return 0
    processed = 0
    for raw_f in fetch_custom_fields(access_token):
        if not raw_f.crm_id:
            continue
        _upsert_custom_field_def(
            sess,
            schema=schema,
            entity_type=raw_f.entity_type,
            field_external_id=raw_f.crm_id,
            field_name=raw_f.name,
            field_code=raw_f.code,
            field_type=raw_f.field_type,
            raw_metadata=raw_f.raw_payload,
        )
        processed += 1
        _report_stage_items(progress, processed)
    if processed:
        _report_stage_items(progress, processed, every=1)
    return processed


def _find_stage_external_id(value: Any) -> str | None:
    """Best-effort recursive extraction of amoCRM status/stage id from event JSON."""
    if isinstance(value, dict):
        for key in ("status_id", "stage_id"):
            if value.get(key) is not None:
                return str(value.get(key))
        lead_status = value.get("lead_status")
        if isinstance(lead_status, dict):
            for key in ("id", "status_id"):
                if lead_status.get(key) is not None:
                    return str(lead_status.get(key))
        for item in value.values():
            nested = _find_stage_external_id(item)
            if nested:
                return nested
    if isinstance(value, list):
        for item in value:
            nested = _find_stage_external_id(item)
            if nested:
                return nested
    return None


def _event_stage_transition(payload: dict[str, Any]) -> tuple[str | None, str | None] | None:
    event_type = str(payload.get("type") or payload.get("event_type") or "").lower()
    before = payload.get("value_before")
    after = payload.get("value_after")
    from_stage = _find_stage_external_id(before)
    to_stage = _find_stage_external_id(after)
    if from_stage or to_stage:
        return from_stage, to_stage
    if any(part in event_type for part in ("status", "stage", "pipeline")):
        return None, _find_stage_external_id(payload)
    return None


def _pull_stage_transitions(
    sess,
    *,
    schema: str,
    deal_map: dict[str, str],
    stage_map: dict[str, str],
    user_map: dict[str, str],
) -> int:
    """Normalize raw amoCRM events into deal stage transition rows."""
    q_schema = f'"{schema}"'
    rows = sess.execute(
        text(
            f"SELECT external_id, payload "
            f"FROM {q_schema}.raw_events "
            "WHERE payload->>'entity_type' IN ('lead', 'leads') "
            "OR payload ? 'value_after' "
            "OR payload ? 'value_before'"
        )
    ).fetchall()
    processed = 0
    for external_id, payload in rows:
        if not isinstance(payload, dict):
            continue
        transition = _event_stage_transition(payload)
        if transition is None:
            continue
        entity_id = payload.get("entity_id")
        deal_uuid = deal_map.get(str(entity_id)) if entity_id is not None else None
        if not deal_uuid:
            continue
        from_stage_ext, to_stage_ext = transition
        from_stage_uuid = stage_map.get(str(from_stage_ext)) if from_stage_ext else None
        to_stage_uuid = stage_map.get(str(to_stage_ext)) if to_stage_ext else None
        if not from_stage_uuid and not to_stage_uuid:
            continue
        changed_by = payload.get("created_by")
        changed_by_uuid = user_map.get(str(changed_by)) if changed_by is not None else None
        created_at = None
        created_raw = payload.get("created_at")
        if isinstance(created_raw, (int, float)):
            created_at = datetime.fromtimestamp(int(created_raw), tz=timezone.utc)
        sess.execute(
            text(
                f"INSERT INTO {q_schema}.deal_stage_transitions("
                "id, deal_id, event_external_id, from_stage_id, to_stage_id, "
                "changed_by_user_id, changed_at_external, raw_metadata, fetched_at"
                ") VALUES (CAST(:id AS UUID), CAST(:deal_id AS UUID), :event_external_id, "
                "CAST(NULLIF(:from_stage_id, '') AS UUID), "
                "CAST(NULLIF(:to_stage_id, '') AS UUID), "
                "CAST(NULLIF(:changed_by_user_id, '') AS UUID), "
                ":changed_at, CAST(:raw_metadata AS JSONB), NOW()) "
                "ON CONFLICT (event_external_id) DO UPDATE SET "
                "  deal_id = EXCLUDED.deal_id, from_stage_id = EXCLUDED.from_stage_id, "
                "  to_stage_id = EXCLUDED.to_stage_id, "
                "  changed_by_user_id = EXCLUDED.changed_by_user_id, "
                "  changed_at_external = EXCLUDED.changed_at_external, "
                "  raw_metadata = EXCLUDED.raw_metadata, fetched_at = NOW()"
            ),
            {
                "id": _uuid(),
                "deal_id": deal_uuid,
                "event_external_id": str(external_id),
                "from_stage_id": from_stage_uuid or "",
                "to_stage_id": to_stage_uuid or "",
                "changed_by_user_id": changed_by_uuid or "",
                "changed_at": created_at,
                "raw_metadata": _json_dumps(payload),
            },
        )
        processed += 1
    return processed


def _pull_tasks(
    sess,
    connector,
    access_token: str,
    *,
    user_map: dict[str, str],
    deal_map: dict[str, str],
    contact_map: dict[str, str],
    since: datetime | None,
    schema: str,
    progress: Callable[[int], None] | None = None,
) -> int:
    """Pull amoCRM tasks into raw_tasks + normalized tasks."""
    processed = 0
    q_schema = f'"{schema}"'
    for raw_t in connector.fetch_tasks(access_token, since=since):
        ext_id = raw_t.crm_id
        if not ext_id:
            continue
        _upsert_raw(sess, schema, "raw_tasks", ext_id, raw_t.raw_payload)
        deal_uuid = deal_map.get(raw_t.deal_id) if raw_t.deal_id else None
        contact_uuid = contact_map.get(raw_t.contact_id) if raw_t.contact_id else None
        resp_uuid = user_map.get(raw_t.responsible_user_id) if raw_t.responsible_user_id else None
        _ = contact_uuid
        sess.execute(
            text(
                f"INSERT INTO {q_schema}.tasks(id, external_id, deal_id, responsible_user_id, "
                "kind, text, is_completed, due_at_external, completed_at_external, fetched_at) "
                "VALUES (CAST(:id AS UUID), :ext, CAST(NULLIF(:deal_id, '') AS UUID), "
                "CAST(NULLIF(:user_id, '') AS UUID), :kind, :text_body, :completed, :due_at, :completed_at, NOW()) "
                "ON CONFLICT (external_id) DO UPDATE SET "
                "  deal_id = EXCLUDED.deal_id, responsible_user_id = EXCLUDED.responsible_user_id, "
                "  kind = EXCLUDED.kind, text = EXCLUDED.text, is_completed = EXCLUDED.is_completed, "
                "  due_at_external = EXCLUDED.due_at_external, "
                "  completed_at_external = EXCLUDED.completed_at_external, fetched_at = NOW()"
            ),
            {
                "id": _uuid(),
                "ext": ext_id,
                "deal_id": deal_uuid or "",
                "user_id": resp_uuid or "",
                "kind": raw_t.kind,
                "text_body": raw_t.text,
                "completed": bool(raw_t.is_completed),
                "due_at": raw_t.due_at,
                "completed_at": raw_t.completed_at,
            },
        )
        _sync_custom_field_values(
            sess,
            schema=schema,
            entity_type="task",
            entity_external_id=ext_id,
            payload=raw_t.raw_payload,
        )
        processed += 1
        _report_stage_items(progress, processed)
    if processed:
        _report_stage_items(progress, processed, every=1)
    return processed


def _pull_products(
    sess,
    connector,
    access_token: str,
    *,
    since: datetime | None,
    schema: str,
    progress: Callable[[int], None] | None = None,
) -> int:
    """Pull catalog/list elements into raw_products + normalized products."""
    fetch_products = getattr(connector, "fetch_products", None)
    if not callable(fetch_products):
        return 0
    processed = 0
    q_schema = f'"{schema}"'
    for raw_p in fetch_products(access_token, since=since):
        ext_id = raw_p.crm_id
        if not ext_id:
            continue
        _upsert_raw(sess, schema, "raw_products", ext_id, raw_p.raw_payload)
        price_cents = int(round(float(raw_p.price) * 100)) if raw_p.price is not None else None
        sess.execute(
            text(
                f"INSERT INTO {q_schema}.products(id, external_id, name, price_cents, currency, fetched_at) "
                "VALUES (CAST(:id AS UUID), :ext, :name, :price, :currency, NOW()) "
                "ON CONFLICT (external_id) DO UPDATE SET "
                "  name = EXCLUDED.name, price_cents = EXCLUDED.price_cents, "
                "  currency = EXCLUDED.currency, fetched_at = NOW()"
            ),
            {
                "id": _uuid(),
                "ext": ext_id,
                "name": raw_p.name,
                "price": price_cents,
                "currency": raw_p.currency,
            },
        )
        _sync_custom_field_values(
            sess,
            schema=schema,
            entity_type="product",
            entity_external_id=ext_id,
            payload=raw_p.raw_payload,
        )
        processed += 1
        _report_stage_items(progress, processed)
    if processed:
        _report_stage_items(progress, processed, every=1)
    return processed


def _call_values_from_note(payload: dict[str, Any]) -> dict[str, Any] | None:
    note_type = str(payload.get("note_type") or "")
    if note_type not in {"call_in", "call_out"}:
        return None
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    return {
        "direction": "in" if note_type == "call_in" else "out",
        "duration": params.get("duration") or params.get("call_duration"),
        "result": params.get("call_result") or params.get("result"),
        "recording_url": params.get("link") or params.get("recording_url"),
    }


def _pull_notes(
    sess,
    connector,
    access_token: str,
    *,
    user_map: dict[str, str],
    deal_map: dict[str, str],
    contact_map: dict[str, str],
    since: datetime | None,
    schema: str,
    progress: Callable[[int], None] | None = None,
) -> tuple[int, int]:
    """Pull lead notes and normalize call notes into calls."""
    processed = 0
    calls_processed = 0
    q_schema = f'"{schema}"'
    for raw_n in connector.fetch_notes(access_token, since=since):
        ext_id = raw_n.crm_id
        if not ext_id:
            continue
        _upsert_raw(sess, schema, "raw_notes", ext_id, raw_n.raw_payload)
        deal_uuid = deal_map.get(raw_n.deal_id) if raw_n.deal_id else None
        contact_uuid = contact_map.get(raw_n.contact_id) if raw_n.contact_id else None
        author_uuid = user_map.get(raw_n.author_user_id) if raw_n.author_user_id else None
        sess.execute(
            text(
                f"INSERT INTO {q_schema}.notes(id, external_id, deal_id, contact_id, author_user_id, "
                "body, created_at_external, fetched_at) "
                "VALUES (CAST(:id AS UUID), :ext, CAST(NULLIF(:deal_id, '') AS UUID), "
                "CAST(NULLIF(:contact_id, '') AS UUID), CAST(NULLIF(:author_id, '') AS UUID), "
                ":body, :created_at, NOW()) "
                "ON CONFLICT (external_id) DO UPDATE SET "
                "  deal_id = EXCLUDED.deal_id, contact_id = EXCLUDED.contact_id, "
                "  author_user_id = EXCLUDED.author_user_id, body = EXCLUDED.body, "
                "  created_at_external = EXCLUDED.created_at_external, fetched_at = NOW()"
            ),
            {
                "id": _uuid(),
                "ext": ext_id,
                "deal_id": deal_uuid or "",
                "contact_id": contact_uuid or "",
                "author_id": author_uuid or "",
                "body": raw_n.body,
                "created_at": raw_n.created_at,
            },
        )
        if isinstance(raw_n.raw_payload, dict):
            call_values = _call_values_from_note(raw_n.raw_payload)
            if call_values is not None:
                _upsert_raw(sess, schema, "raw_calls", ext_id, raw_n.raw_payload)
                sess.execute(
                    text(
                        f"INSERT INTO {q_schema}.calls(id, external_id, deal_id, contact_id, user_id, "
                        "direction, duration_sec, result, started_at_external, transcript_ref, fetched_at) "
                        "VALUES (CAST(:id AS UUID), :ext, CAST(NULLIF(:deal_id, '') AS UUID), "
                        "CAST(NULLIF(:contact_id, '') AS UUID), CAST(NULLIF(:user_id, '') AS UUID), "
                        ":direction, :duration, :result, :started_at, CAST(:transcript AS JSONB), NOW()) "
                        "ON CONFLICT (external_id) DO UPDATE SET "
                        "  deal_id = EXCLUDED.deal_id, contact_id = EXCLUDED.contact_id, "
                        "  user_id = EXCLUDED.user_id, direction = EXCLUDED.direction, "
                        "  duration_sec = EXCLUDED.duration_sec, result = EXCLUDED.result, "
                        "  started_at_external = EXCLUDED.started_at_external, "
                        "  transcript_ref = EXCLUDED.transcript_ref, fetched_at = NOW()"
                    ),
                    {
                        "id": _uuid(),
                        "ext": ext_id,
                        "deal_id": deal_uuid or "",
                        "contact_id": contact_uuid or "",
                        "user_id": author_uuid or "",
                        "direction": call_values["direction"],
                        "duration": _int_or_none(call_values.get("duration")),
                        "result": call_values.get("result"),
                        "started_at": raw_n.created_at,
                        "transcript": json.dumps(
                            {"recording_url": call_values.get("recording_url")},
                            ensure_ascii=False,
                        ),
                    },
                )
                calls_processed += 1
        processed += 1
        _report_stage_items(progress, processed)
    if processed:
        _report_stage_items(progress, processed, every=1)
    return processed, calls_processed


def _pull_events(
    sess,
    connector,
    access_token: str,
    *,
    since: datetime | None,
    limit: int | None = None,
    schema: str,
    progress: Callable[[int], None] | None = None,
) -> int:
    """Pull raw amoCRM events for stage history and timeline analytics."""
    processed = 0
    for raw_e in connector.fetch_events(access_token, since=since, limit=limit):
        ext_id = raw_e.crm_id
        if not ext_id:
            continue
        _upsert_raw(sess, schema, "raw_events", ext_id, raw_e.raw_payload)
        processed += 1
        _report_stage_items(progress, processed)
    if processed:
        _report_stage_items(progress, processed, every=1)
    return processed


def _pull_timeline_messages(
    sess,
    connector,
    access_token: str,
    *,
    user_map: dict[str, str],
    contact_map: dict[str, str],
    deal_rows: list[tuple[str, str]],
    contact_rows: list[tuple[str, str]] | None = None,
    created_from: datetime | None,
    created_to: datetime | None,
    limit: int | None = None,
    entity_limit: int | None = None,
    schema: str,
    progress: Callable[[int], None] | None = None,
) -> tuple[int, int, dict[str, Any]]:
    """Pull experimental amoCRM lead/contact timeline messages into chats/messages."""
    fetch_deal_messages = getattr(connector, "fetch_lead_timeline_messages", None)
    fetch_contact_messages = getattr(connector, "fetch_contact_timeline_messages", None)
    if not callable(fetch_deal_messages) and not callable(fetch_contact_messages):
        return 0, 0, {"skipped_reason": "timeline_fetcher_missing"}
    q_schema = f'"{schema}"'
    deal_uuid_by_external = {external_id: deal_uuid for external_id, deal_uuid in deal_rows}
    contact_uuid_by_external = {
        external_id: contact_uuid for external_id, contact_uuid in (contact_rows or [])
    }
    processed = 0
    seen_chats: set[str] = set()
    skipped: list[str] = []
    scoped_deal_rows = deal_rows or []
    scoped_contact_rows = contact_rows or []
    if entity_limit is not None:
        if entity_limit <= 0:
            skipped.append("timeline_entity_scan_disabled")
            scoped_deal_rows = []
            scoped_contact_rows = []
        else:
            if len(scoped_deal_rows) > entity_limit:
                skipped.append("deal_entity_limit_reached")
                scoped_deal_rows = scoped_deal_rows[:entity_limit]
            if len(scoped_contact_rows) > entity_limit:
                skipped.append("contact_entity_limit_reached")
                scoped_contact_rows = scoped_contact_rows[:entity_limit]

    def upsert_message(raw_m) -> None:
        nonlocal processed
        ext_id = raw_m.crm_id
        if not ext_id:
            return
        _upsert_raw(sess, schema, "raw_messages", ext_id, raw_m.raw_payload)
        deal_uuid = deal_uuid_by_external.get(raw_m.deal_id or "")
        contact_uuid = (
            contact_uuid_by_external.get(raw_m.contact_id or "")
            or contact_map.get(raw_m.contact_id)
            if raw_m.contact_id
            else None
        )
        author_uuid = user_map.get(raw_m.author_user_id) if raw_m.author_user_id else None
        chat_external_id = raw_m.chat_id or f"deal:{raw_m.deal_id or 'contact:' + str(raw_m.contact_id or ext_id)}"
        seen_chats.add(chat_external_id)
        _upsert_raw(
            sess,
            schema,
            "raw_chats",
            chat_external_id,
            {
                "external_id": chat_external_id,
                "deal_id": raw_m.deal_id,
                "contact_id": raw_m.contact_id,
                "channel": raw_m.channel,
                "source": "amocrm_ajax_events_timeline",
            },
        )
        chat_result = sess.execute(
            text(
                f"INSERT INTO {q_schema}.chats(id, external_id, channel, deal_id, contact_id, "
                "started_at_external, fetched_at) "
                "VALUES (CAST(:id AS UUID), :ext, :channel, CAST(NULLIF(:deal_id, '') AS UUID), "
                "CAST(NULLIF(:contact_id, '') AS UUID), :started_at, NOW()) "
                "ON CONFLICT (external_id) DO UPDATE SET "
                "  channel = EXCLUDED.channel, deal_id = COALESCE(EXCLUDED.deal_id, chats.deal_id), "
                "  contact_id = COALESCE(EXCLUDED.contact_id, chats.contact_id), "
                "  started_at_external = COALESCE(chats.started_at_external, EXCLUDED.started_at_external), "
                "  fetched_at = NOW() "
                "RETURNING id"
            ),
            {
                "id": _uuid(),
                "ext": chat_external_id,
                "channel": raw_m.channel,
                "deal_id": deal_uuid or "",
                "contact_id": contact_uuid or "",
                "started_at": raw_m.sent_at,
            },
        )
        chat_row = chat_result.fetchone()
        chat_uuid = str(chat_row[0]) if chat_row and chat_row[0] else None
        author_kind = raw_m.author_kind if raw_m.author_kind in {"user", "client", "system"} else "system"
        sess.execute(
            text(
                f"INSERT INTO {q_schema}.messages(id, external_id, chat_id, author_kind, "
                "author_user_id, text, sent_at_external, fetched_at) "
                "VALUES (CAST(:id AS UUID), :ext, CAST(NULLIF(:chat_id, '') AS UUID), "
                ":author_kind, CAST(NULLIF(:author_id, '') AS UUID), :text_body, :sent_at, NOW()) "
                "ON CONFLICT (external_id) DO UPDATE SET "
                "  chat_id = EXCLUDED.chat_id, author_kind = EXCLUDED.author_kind, "
                "  author_user_id = EXCLUDED.author_user_id, text = EXCLUDED.text, "
                "  sent_at_external = EXCLUDED.sent_at_external, fetched_at = NOW()"
            ),
            {
                "id": _uuid(),
                "ext": ext_id,
                "chat_id": chat_uuid or "",
                "author_kind": author_kind,
                "author_id": author_uuid or "",
                "text_body": raw_m.text,
                "sent_at": raw_m.sent_at,
            },
        )
        processed += 1
        _report_stage_items(progress, processed)

    try:
        if callable(fetch_deal_messages) and scoped_deal_rows:
            for raw_m in fetch_deal_messages(
                access_token,
                [external_id for external_id, _ in scoped_deal_rows],
                created_from=created_from,
                created_to=created_to,
                limit=limit,
            ):
                if limit is not None and processed >= limit:
                    break
                upsert_message(raw_m)
    except Exception as exc:
        logger.warning(
            "amocrm_timeline_messages_import_skipped",
            extra={"schema": schema, "scope": "deals", "error_type": type(exc).__name__},
        )
        skipped.append(f"deals:{type(exc).__name__}")

    try:
        remaining_limit = None if limit is None else max(0, limit - processed)
        if callable(fetch_contact_messages) and scoped_contact_rows and remaining_limit != 0:
            for raw_m in fetch_contact_messages(
                access_token,
                [external_id for external_id, _ in scoped_contact_rows],
                created_from=created_from,
                created_to=created_to,
                limit=remaining_limit,
            ):
                if limit is not None and processed >= limit:
                    break
                upsert_message(raw_m)
    except Exception as exc:
        logger.warning(
            "amocrm_timeline_messages_import_skipped",
            extra={"schema": schema, "scope": "contacts", "error_type": type(exc).__name__},
        )
        skipped.append(f"contacts:{type(exc).__name__}")

    inbox_coverage = _pull_inbox_chats_best_effort(
        sess,
        connector,
        access_token,
        schema=schema,
        deal_uuid_by_external=deal_uuid_by_external,
        contact_uuid_by_external=contact_uuid_by_external,
        created_from=created_from,
        created_to=created_to,
        limit=None if limit is None else max(0, limit - processed),
    )

    inbox_messages = int(inbox_coverage.get("messages_imported", 0) or 0)
    total_processed = processed + inbox_messages
    if total_processed:
        _report_stage_items(progress, total_processed, every=1)
    coverage = {
        "messages_imported": total_processed,
        "chats_seen": len(seen_chats) + int(inbox_coverage.get("chats_seen", 0)),
        "chats_matched": int(inbox_coverage.get("chats_matched", 0)),
        "unmatched_chats": int(inbox_coverage.get("unmatched_chats", 0)),
        "deals_scanned": len(scoped_deal_rows),
        "contacts_scanned": len(scoped_contact_rows),
        "skipped_reason": (
            ";".join(skipped)
            if skipped
            else "limit_reached"
            if limit is not None and total_processed >= limit
            else inbox_coverage.get("skipped_reason")
        ),
    }
    return total_processed, len(seen_chats) + int(inbox_coverage.get("chats_matched", 0)), coverage


def _pull_inbox_chats_best_effort(
    sess,
    connector,
    access_token: str,
    *,
    schema: str,
    deal_uuid_by_external: dict[str, str],
    contact_uuid_by_external: dict[str, str],
    created_from: datetime | None,
    created_to: datetime | None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Scan amoCRM inbox list and keep only chats matched to selected scope."""
    fetch_inbox_chats = getattr(connector, "fetch_inbox_chats", None)
    if not callable(fetch_inbox_chats):
        return {"skipped_reason": "inbox_fetcher_missing", "chats_seen": 0, "chats_matched": 0, "unmatched_chats": 0}
    q_schema = f'"{schema}"'
    seen = 0
    matched = 0
    unmatched = 0
    inbox_messages = 0
    seen_message_ids: set[str] = set()
    try:
        for chat in fetch_inbox_chats(
            access_token,
            created_from=created_from,
            created_to=created_to,
            limit=limit,
        ):
            if not isinstance(chat, dict):
                continue
            seen += 1
            chat_id = (
                chat.get("id")
                or chat.get("talk_id")
                or chat.get("conversation_id")
                or chat.get("chat_id")
            )
            if chat_id is None:
                unmatched += 1
                continue
            entity_obj = chat.get("entity") if isinstance(chat.get("entity"), dict) else {}
            contact_obj = chat.get("contact") if isinstance(chat.get("contact"), dict) else {}
            deal_external_id = chat.get("lead_id") or chat.get("entity_id") or entity_obj.get("id")
            contact_external_id = chat.get("contact_id") or contact_obj.get("id")
            deal_uuid = deal_uuid_by_external.get(str(deal_external_id)) if deal_external_id else None
            contact_uuid = (
                contact_uuid_by_external.get(str(contact_external_id))
                if contact_external_id
                else None
            )
            if not deal_uuid and not contact_uuid:
                unmatched += 1
                continue
            matched += 1
            chat_external_id = str(chat_id)
            _upsert_raw(sess, schema, "raw_chats", chat_external_id, chat)
            channel = str(
                chat.get("chat_source")
                or chat.get("channel")
                or chat.get("source")
                or "amocrm"
            )
            chat_result = sess.execute(
                text(
                    f"INSERT INTO {q_schema}.chats(id, external_id, channel, deal_id, contact_id, "
                    "started_at_external, fetched_at) "
                    "VALUES (CAST(:id AS UUID), :ext, :channel, CAST(NULLIF(:deal_id, '') AS UUID), "
                    "CAST(NULLIF(:contact_id, '') AS UUID), :started_at, NOW()) "
                    "ON CONFLICT (external_id) DO UPDATE SET "
                    "  channel = EXCLUDED.channel, deal_id = COALESCE(EXCLUDED.deal_id, chats.deal_id), "
                    "  contact_id = COALESCE(EXCLUDED.contact_id, chats.contact_id), "
                    "  started_at_external = COALESCE(chats.started_at_external, EXCLUDED.started_at_external), "
                    "  fetched_at = NOW() "
                    "RETURNING id"
                ),
                {
                    "id": _uuid(),
                    "ext": chat_external_id,
                    "channel": channel,
                    "deal_id": deal_uuid or "",
                    "contact_id": contact_uuid or "",
                    "started_at": None,
                },
            )
            chat_row = chat_result.fetchone()
            chat_uuid = str(chat_row[0]) if chat_row and chat_row[0] else None
            last_message = chat.get("last_message") if isinstance(chat.get("last_message"), dict) else {}
            text_body = last_message.get("text")
            if isinstance(text_body, str) and text_body.strip():
                last_message_raw_id = last_message.get("id")
                sent_at_raw = (
                    last_message.get("last_message_at")
                    or last_message.get("created_at")
                    or chat.get("updated_at")
                    or chat.get("created_at")
                )
                sent_at = None
                try:
                    if sent_at_raw is not None:
                        sent_at = datetime.fromtimestamp(int(float(sent_at_raw)), tz=timezone.utc)
                except (TypeError, ValueError, OverflowError):
                    sent_at = None
                message_external_id = (
                    str(last_message_raw_id)
                    if last_message_raw_id is not None
                    else f"inbox_last:{chat_external_id}:{sent_at_raw or 'unknown'}"
                )
                already_seen_message = message_external_id in seen_message_ids
                seen_message_ids.add(message_external_id)
                _upsert_raw(
                    sess,
                    schema,
                    "raw_messages",
                    message_external_id,
                    {
                        **last_message,
                        "_code9_source": "amocrm_ajax_inbox_last_message",
                        "_code9_chat_id": chat_external_id,
                        "_code9_deal_id": deal_external_id,
                        "_code9_contact_id": contact_external_id,
                    },
                )
                contact_name = contact_obj.get("name") if isinstance(contact_obj, dict) else None
                author = last_message.get("author")
                chat_type = str(chat.get("type") or "").lower()
                author_kind = (
                    "client"
                    if (
                        (isinstance(author, str) and isinstance(contact_name, str) and author == contact_name)
                        or "incoming" in chat_type
                        or "reply" in chat_type
                    )
                    else "user"
                )
                sess.execute(
                    text(
                        f"INSERT INTO {q_schema}.messages(id, external_id, chat_id, author_kind, "
                        "author_user_id, text, sent_at_external, fetched_at) "
                        "VALUES (CAST(:id AS UUID), :ext, CAST(NULLIF(:chat_id, '') AS UUID), "
                        ":author_kind, NULL, :text_body, :sent_at, NOW()) "
                        "ON CONFLICT (external_id) DO UPDATE SET "
                        "  chat_id = EXCLUDED.chat_id, author_kind = EXCLUDED.author_kind, "
                        "  text = EXCLUDED.text, sent_at_external = EXCLUDED.sent_at_external, "
                        "  fetched_at = NOW()"
                    ),
                    {
                        "id": _uuid(),
                        "ext": message_external_id,
                        "chat_id": chat_uuid or "",
                        "author_kind": author_kind,
                        "text_body": text_body,
                        "sent_at": sent_at,
                    },
                )
                if not already_seen_message:
                    inbox_messages += 1
    except Exception as exc:
        logger.warning(
            "amocrm_inbox_chat_import_skipped",
            extra={"schema": schema, "error_type": type(exc).__name__},
        )
        return {
            "skipped_reason": f"inbox:{type(exc).__name__}",
            "chats_seen": seen,
            "chats_matched": matched,
            "unmatched_chats": unmatched,
            "messages_imported": inbox_messages,
        }
    return {
        "chats_seen": seen,
        "chats_matched": matched,
        "unmatched_chats": unmatched,
        "messages_imported": inbox_messages,
    }


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Public job entrypoint
# ---------------------------------------------------------------------------

def pull_amocrm_core(
    connection_id: str,
    *,
    first_pull: bool = False,
    since_iso: str | None = None,
    date_from_iso: str | None = None,
    date_to_iso: str | None = None,
    pipeline_ids: list[str] | None = None,
    cleanup_trial: bool = False,
    deals_limit: int | None = None,
    contacts_limit: int | None = None,
    export_estimate: dict[str, Any] | None = None,
    export_scope: str | None = None,
    messages_limit: int | None = None,
    messages_entity_limit: int | None = None,
    events_limit: int | None = None,
    auto_sync: bool = False,
    job_row_id: str | None = None,
) -> dict[str, Any]:
    """
    Phase 2A pull: pipelines + stages + users + contacts + deals.

    Args:
        connection_id: UUID из ``public.crm_connections``.
        first_pull: True только после OAuth-callback'а. В MOCK-режиме
            делегирует ``trial_export``, чтобы FE увидел данные.
        since_iso: ISO-8601 UTC timestamp. ``None`` → полный дамп.
        date_from_iso / date_to_iso: пользовательский аналитический срез по
            ``created_at`` сделки. Даты без времени трактуются как начало и
            конец дня UTC.
        pipeline_ids: external amoCRM pipeline ids. ``None`` / ``[]`` → все.
        cleanup_trial: удалить только Code9 trial rows ``ext-*`` перед
            реальной выгрузкой, чтобы mock-данные не смешались с amoCRM.
        deals_limit / contacts_limit: верхние отсечки (для trial/audit).
        export_estimate: UI/API estimate snapshot stored in public.jobs.payload.
            Worker does not need it for import logic, but accepts it because
            enqueue passes payload keys as kwargs.
        export_scope: ``None`` для основной выгрузки, ``messages`` или
            ``events`` для безопасной отдельной догрузки тяжёлых слоёв.
        messages_limit / messages_entity_limit / events_limit: верхние отсечки
            для scoped-догрузок.
        auto_sync: True для scheduler-driven incremental sync.
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
                    "companies": export_result.get("companies_created", 0),
                    "contacts": export_result.get("contacts_created", 0),
                    "deals": export_result.get("deals_created", 0),
                },
                "audit_job_enqueued": audit_enqueued,
            }
            charge_token_reservation_for_job(job_row_id, result)
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
        conn_metadata = conn_info.get("metadata") if isinstance(conn_info.get("metadata"), dict) else {}
        previous_active_export = (
            conn_metadata.get("active_export")
            if isinstance(conn_metadata.get("active_export"), dict)
            else {}
        )
        preserve_active_export = (
            since_iso is not None
            and date_from_iso is None
            and date_to_iso is None
            and pipeline_ids is None
        )
        effective_date_from_iso = (
            previous_active_export.get("date_from")
            if preserve_active_export
            else date_from_iso
        )
        effective_date_to_iso = (
            previous_active_export.get("date_to")
            if preserve_active_export
            else date_to_iso
        )
        effective_pipeline_ids = (
            previous_active_export.get("pipeline_ids")
            if preserve_active_export
            else pipeline_ids
        )
        if preserve_active_export and effective_date_from_iso == "2000-01-01":
            # The UI's "all time" preset should keep growing after the first
            # full export, otherwise new deals created after the original
            # export date would never enter the active analytics slice.
            effective_date_to_iso = datetime.now(tz=timezone.utc).date().isoformat()
        created_from = _parse_export_date_start(effective_date_from_iso)
        created_to = _parse_export_date_end(effective_date_to_iso)
        selected_pipeline_ids = [
            str(pid) for pid in (effective_pipeline_ids or []) if str(pid).strip()
        ]

        q_schema = f'"{schema}"'
        counts: dict[str, int] = {}
        messages_coverage: dict[str, Any] = {}
        scoped_export = export_scope if export_scope in {"messages", "events"} else None
        total_steps = 4 if scoped_export else 6 if first_pull else 16

        with sync_session() as sess:
            # Task #52.7: schema qualified в каждом INSERT внутри _pull_*
            # (см. ``_upsert_raw`` / _pull_pipelines / _pull_stages / _pull_users /
            # _pull_contacts / _pull_deals). SET LOCAL оставлен как
            # belt-and-suspenders для возможных будущих raw SQL-statement'ов.
            sess.execute(text(f"SET LOCAL search_path = {q_schema}, public"))

            logger.info(
                "crm_pull_started",
                extra={"connection_id": connection_id, "schema": schema, "first_pull": first_pull},
            )

            if scoped_export:
                deal_map = _load_external_id_map(sess, schema=schema, table="deals")
                contact_map = _load_external_id_map(sess, schema=schema, table="contacts")
                stage_map = _load_external_id_map(sess, schema=schema, table="stages")
                user_map = _load_external_id_map(sess, schema=schema, table="crm_users")
                selected_deal_rows = _load_selected_deal_rows(
                    sess,
                    schema=schema,
                    created_from=created_from,
                    created_to=created_to,
                    pipeline_ids=selected_pipeline_ids,
                )
                selected_contact_rows = _load_selected_contact_rows(
                    sess,
                    schema=schema,
                    created_from=created_from,
                    created_to=created_to,
                    pipeline_ids=selected_pipeline_ids,
                )
                counts = _tenant_active_export_counts(
                    sess,
                    schema=schema,
                    created_from=created_from,
                    created_to=created_to,
                    pipeline_ids=selected_pipeline_ids,
                )
                update_job_progress(
                    job_row_id,
                    stage="contacts_scope",
                    completed_steps=1,
                    total_steps=total_steps,
                    counts={
                        **counts,
                        "selected_deals": len(selected_deal_rows),
                        "selected_contacts": len(selected_contact_rows),
                    },
                )

                if scoped_export == "messages":
                    message_limit = max(
                        1,
                        int(messages_limit or AMOCRM_MESSAGES_IMPORT_LIMIT_DEFAULT),
                    )
                    message_entity_limit = max(
                        0,
                        int(
                            AMOCRM_MESSAGES_ENTITY_LIMIT_DEFAULT
                            if messages_entity_limit is None
                            else messages_entity_limit
                        ),
                    )
                    logger.info(
                        "amocrm_messages_import",
                        extra={
                            "schema": schema,
                            "limit": message_limit,
                            "entity_limit": message_entity_limit,
                        },
                    )
                    messages_processed, chats_processed, messages_coverage = _pull_timeline_messages(
                        sess,
                        connector,
                        access_token,
                        user_map=user_map,
                        contact_map=contact_map,
                        deal_rows=selected_deal_rows,
                        contact_rows=selected_contact_rows,
                        created_from=created_from,
                        created_to=created_to,
                        limit=message_limit,
                        entity_limit=message_entity_limit,
                        schema=schema,
                        progress=lambda n: update_job_progress(
                            job_row_id,
                            stage="messages",
                            completed_steps=2,
                            total_steps=total_steps,
                            counts={**counts, "messages_imported": n},
                        ),
                    )
                    counts = _tenant_active_export_counts(
                        sess,
                        schema=schema,
                        created_from=created_from,
                        created_to=created_to,
                        pipeline_ids=selected_pipeline_ids,
                    )
                    update_job_progress(
                        job_row_id,
                        stage="messages",
                        completed_steps=4,
                        total_steps=total_steps,
                        counts={
                            **counts,
                            "messages_processed": messages_processed,
                            "chats_processed": chats_processed,
                            "messages_chats_seen": int(messages_coverage.get("chats_seen", 0) or 0),
                            "messages_chats_matched": int(messages_coverage.get("chats_matched", 0) or 0),
                            "messages_unmatched_chats": int(messages_coverage.get("unmatched_chats", 0) or 0),
                            "message_deals_scanned": int(messages_coverage.get("deals_scanned", 0) or 0),
                            "message_contacts_scanned": int(messages_coverage.get("contacts_scanned", 0) or 0),
                        },
                    )
                    metadata_extra = {
                        "last_messages_pull_counts": counts,
                        "last_messages_pull_at": datetime.now(tz=timezone.utc).isoformat(),
                    }
                    notification_title = "Догрузка сообщений amoCRM завершена"
                    notification_body = (
                        f"Сообщений: {counts.get('messages', 0)}, "
                        f"чатов: {counts.get('chats', 0)}."
                    )
                if scoped_export == "events":
                    event_limit = max(
                        1,
                        int(events_limit or AMOCRM_EVENTS_IMPORT_LIMIT_DEFAULT),
                    )
                    logger.info(
                        "amocrm_events_import",
                        extra={"schema": schema, "limit": event_limit},
                    )
                    events_processed = _pull_events(
                        sess,
                        connector,
                        access_token,
                        since=created_from,
                        limit=event_limit,
                        schema=schema,
                        progress=lambda n: update_job_progress(
                            job_row_id,
                            stage="events",
                            completed_steps=2,
                            total_steps=total_steps,
                            counts={**counts, "events_imported": n},
                        ),
                    )
                    stage_transitions_processed = _pull_stage_transitions(
                        sess,
                        schema=schema,
                        deal_map=deal_map,
                        stage_map=stage_map,
                        user_map=user_map,
                    )
                    counts = _tenant_active_export_counts(
                        sess,
                        schema=schema,
                        created_from=created_from,
                        created_to=created_to,
                        pipeline_ids=selected_pipeline_ids,
                    )
                    update_job_progress(
                        job_row_id,
                        stage="stage_transitions",
                        completed_steps=4,
                        total_steps=total_steps,
                        counts={
                            **counts,
                            "events_processed": events_processed,
                            "stage_transitions_processed": stage_transitions_processed,
                        },
                    )
                    metadata_extra = {
                        "last_events_pull_counts": counts,
                        "last_events_pull_at": datetime.now(tz=timezone.utc).isoformat(),
                    }
                    notification_title = "Догрузка событий amoCRM завершена"
                    notification_body = (
                        f"Событий: {counts.get('events', 0)}, "
                        f"переходов этапов: {counts.get('stage_transitions', 0)}."
                    )

                active_export = _build_active_export_metadata(
                    date_from_iso=effective_date_from_iso,
                    date_to_iso=effective_date_to_iso,
                    pipeline_ids=selected_pipeline_ids,
                    counts=counts,
                    messages_coverage=messages_coverage if scoped_export == "messages" else None,
                )
                metadata_patch = {
                    "last_pull_counts": counts,
                    "active_export": active_export,
                    **metadata_extra,
                }
                sess.execute(
                    text(
                        "UPDATE crm_connections SET "
                        "  updated_at = NOW(), "
                        "  metadata = COALESCE(metadata, '{}'::jsonb) "
                        "    || CAST(:patch AS JSONB) "
                        "WHERE id = CAST(:cid AS UUID)"
                    ),
                    {
                        "cid": connection_id,
                        "patch": json.dumps(metadata_patch, ensure_ascii=False),
                    },
                )
                result = {
                    "connection_id": connection_id,
                    "mock": False,
                    "first_pull": False,
                    "auto_sync": False,
                    "export_scope": scoped_export,
                    "tenant_schema": schema,
                    "counts": counts,
                    "audit_job_enqueued": False,
                }
                create_job_notification(
                    job_row_id,
                    kind="sync_complete",
                    title=notification_title,
                    body=notification_body,
                    metadata={"counts": counts, "export_scope": scoped_export},
                )
                charge_token_reservation_for_job(job_row_id, result)
                mark_job_succeeded(job_row_id, result)
                return result

            if cleanup_trial:
                _cleanup_trial_export_rows(sess, schema=schema)
                print(f"[pull_amocrm_core] schema={schema} cleanup_trial=done", flush=True)

            pipeline_map = _pull_pipelines(sess, connector, access_token, schema=schema)
            counts["pipelines"] = len(pipeline_map)
            print(
                f"[pull_amocrm_core] schema={schema} pipelines={counts['pipelines']}",
                flush=True,
            )
            update_job_progress(
                job_row_id,
                stage="pipelines",
                completed_steps=1,
                total_steps=total_steps,
                counts=counts,
            )

            stage_map = _pull_stages(
                sess, connector, access_token, pipeline_map, schema=schema
            )
            counts["stages"] = len(stage_map)
            print(
                f"[pull_amocrm_core] schema={schema} stages={counts['stages']}",
                flush=True,
            )
            update_job_progress(
                job_row_id,
                stage="stages",
                completed_steps=2,
                total_steps=total_steps,
                counts=counts,
            )

            user_map = _pull_users(sess, connector, access_token, schema=schema)
            counts["users"] = len(user_map)
            print(
                f"[pull_amocrm_core] schema={schema} users={counts['users']}",
                flush=True,
            )
            update_job_progress(
                job_row_id,
                stage="users",
                completed_steps=3,
                total_steps=total_steps,
                counts=counts,
            )

            _pull_companies(
                sess,
                connector,
                access_token,
                user_map,
                since,
                schema=schema,
                progress=lambda n: update_job_progress(
                    job_row_id,
                    stage="companies",
                    completed_steps=3,
                    total_steps=total_steps,
                    counts={**counts, "companies_imported": n},
                ),
            )
            company_map = _load_external_id_map(sess, schema=schema, table="companies")
            counts["companies"] = len(company_map)
            print(
                f"[pull_amocrm_core] schema={schema} companies={counts['companies']}",
                flush=True,
            )
            update_job_progress(
                job_row_id,
                stage="companies",
                completed_steps=4,
                total_steps=total_steps,
                counts=counts,
            )

            contact_map = _pull_contacts(
                sess,
                connector,
                access_token,
                user_map,
                since,
                contacts_limit,
                schema=schema,
                progress=lambda n: update_job_progress(
                    job_row_id,
                    stage="contacts",
                    completed_steps=4,
                    total_steps=total_steps,
                    counts={**counts, "contacts_imported": n},
                ),
            )
            contact_map = _load_external_id_map(sess, schema=schema, table="contacts")
            counts["contacts"] = len(contact_map)
            print(
                f"[pull_amocrm_core] schema={schema} contacts={counts['contacts']}",
                flush=True,
            )
            update_job_progress(
                job_row_id,
                stage="contacts",
                completed_steps=5,
                total_steps=total_steps,
                counts=counts,
            )

            deals_processed = _pull_deals(
                sess,
                connector,
                access_token,
                pipeline_map=pipeline_map,
                stage_map=stage_map,
                user_map=user_map,
                company_map=company_map,
                contact_map=contact_map,
                since=since,
                created_from=created_from,
                created_to=created_to,
                pipeline_ids=selected_pipeline_ids,
                limit=deals_limit,
                schema=schema,
                progress=lambda n: update_job_progress(
                    job_row_id,
                    stage="deals",
                    completed_steps=5,
                    total_steps=total_steps,
                    counts={**counts, "deals_imported": n},
                ),
            )
            print(
                f"[pull_amocrm_core] schema={schema} deals_processed={deals_processed}",
                flush=True,
            )
            update_job_progress(
                job_row_id,
                stage="deals",
                completed_steps=6,
                total_steps=total_steps,
                counts={**counts, "deals_processed": deals_processed},
            )

            if not first_pull:
                deal_map = _load_external_id_map(sess, schema=schema, table="deals")
                tags_count = _tenant_table_count(sess, schema=schema, table="tags")
                counts["tags"] = tags_count
                counts["deal_contacts"] = _tenant_table_count(
                    sess,
                    schema=schema,
                    table="deal_contacts",
                )
                counts["deal_companies"] = _tenant_table_count(
                    sess,
                    schema=schema,
                    table="deal_companies",
                )
                counts["deal_sources"] = _tenant_table_count(
                    sess,
                    schema=schema,
                    table="deal_sources",
                )

                selected_deal_rows = _load_selected_deal_rows(
                    sess,
                    schema=schema,
                    created_from=created_from,
                    created_to=created_to,
                    pipeline_ids=selected_pipeline_ids,
                )
                selected_contact_rows = _load_selected_contact_rows(
                    sess,
                    schema=schema,
                    created_from=created_from,
                    created_to=created_to,
                    pipeline_ids=selected_pipeline_ids,
                )
                update_job_progress(
                    job_row_id,
                    stage="contacts_scope",
                    completed_steps=7,
                    total_steps=total_steps,
                    counts={
                        **counts,
                        "selected_deals": len(selected_deal_rows),
                        "selected_contacts": len(selected_contact_rows),
                    },
                )

                try:
                    custom_fields_processed = _pull_custom_fields(
                        sess,
                        connector,
                        access_token,
                        schema=schema,
                        progress=lambda n: update_job_progress(
                            job_row_id,
                            stage="custom_fields",
                            completed_steps=7,
                            total_steps=total_steps,
                            counts={**counts, "custom_fields_imported": n},
                        ),
                    )
                except Exception as exc:
                    custom_fields_processed = 0
                    logger.warning(
                        "amocrm_custom_fields_import_skipped",
                        extra={"schema": schema, "error_type": type(exc).__name__},
                    )
                counts["custom_fields"] = _tenant_table_count(
                    sess,
                    schema=schema,
                    table="crm_custom_fields",
                )
                counts["custom_field_values"] = _tenant_table_count(
                    sess,
                    schema=schema,
                    table="crm_custom_field_values",
                )
                update_job_progress(
                    job_row_id,
                    stage="custom_fields",
                    completed_steps=8,
                    total_steps=total_steps,
                    counts={
                        **counts,
                        "custom_fields_processed": custom_fields_processed,
                    },
                )

                update_job_progress(
                    job_row_id,
                    stage="sources",
                    completed_steps=9,
                    total_steps=total_steps,
                    counts=counts,
                )

                products_processed = _pull_products(
                    sess,
                    connector,
                    access_token,
                    since=since,
                    schema=schema,
                    progress=lambda n: update_job_progress(
                        job_row_id,
                        stage="products",
                        completed_steps=9,
                        total_steps=total_steps,
                        counts={**counts, "products_imported": n},
                    ),
                )
                counts["products"] = _tenant_table_count(sess, schema=schema, table="products")
                linked_product_rows = _link_deal_products_to_products(sess, schema=schema)
                counts["deal_products"] = _tenant_table_count(
                    sess,
                    schema=schema,
                    table="deal_products",
                )
                update_job_progress(
                    job_row_id,
                    stage="products",
                    completed_steps=10,
                    total_steps=total_steps,
                    counts={
                        **counts,
                        "products_processed": products_processed,
                        "deal_products_linked": linked_product_rows,
                    },
                )

                tasks_processed = _pull_tasks(
                    sess,
                    connector,
                    access_token,
                    user_map=user_map,
                    deal_map=deal_map,
                    contact_map=contact_map,
                    since=since,
                    schema=schema,
                    progress=lambda n: update_job_progress(
                        job_row_id,
                        stage="tasks",
                        completed_steps=10,
                        total_steps=total_steps,
                        counts={**counts, "tasks_imported": n},
                    ),
                )
                counts["tasks"] = _tenant_table_count(sess, schema=schema, table="tasks")
                update_job_progress(
                    job_row_id,
                    stage="tasks_enriched",
                    completed_steps=11,
                    total_steps=total_steps,
                    counts={**counts, "tasks_processed": tasks_processed},
                )

                if AMOCRM_GLOBAL_NOTES_ENABLED:
                    notes_processed, calls_processed = _pull_notes(
                        sess,
                        connector,
                        access_token,
                        user_map=user_map,
                        deal_map=deal_map,
                        contact_map=contact_map,
                        since=since,
                        schema=schema,
                        progress=lambda n: update_job_progress(
                            job_row_id,
                            stage="notes",
                            completed_steps=11,
                            total_steps=total_steps,
                            counts={**counts, "notes_imported": n},
                        ),
                    )
                    notes_skipped_reason = None
                else:
                    # The global /leads/notes endpoint is not scoped by the
                    # selected export pipelines and can stall large accounts.
                    # Keep this phase non-blocking until notes/calls are
                    # imported through scoped timeline/channel integrations.
                    notes_processed = 0
                    calls_processed = 0
                    notes_skipped_reason = "global_notes_disabled"
                    logger.info(
                        "amocrm_global_notes_import_skipped",
                        extra={"schema": schema, "reason": notes_skipped_reason},
                    )
                counts["notes"] = _tenant_table_count(sess, schema=schema, table="notes")
                counts["calls"] = _tenant_table_count(sess, schema=schema, table="calls")
                update_job_progress(
                    job_row_id,
                    stage="notes",
                    completed_steps=12,
                    total_steps=total_steps,
                    counts={
                        **counts,
                        "notes_processed": notes_processed,
                        "calls_processed": calls_processed,
                        "notes_skipped_reason": notes_skipped_reason,
                    },
                )

                if AMOCRM_TIMELINE_MESSAGES_ENABLED:
                    messages_processed, chats_processed, messages_coverage = _pull_timeline_messages(
                        sess,
                        connector,
                        access_token,
                        user_map=user_map,
                        contact_map=contact_map,
                        deal_rows=selected_deal_rows,
                        contact_rows=selected_contact_rows,
                        created_from=created_from,
                        created_to=created_to,
                        schema=schema,
                        progress=lambda n: update_job_progress(
                            job_row_id,
                            stage="messages",
                            completed_steps=12,
                            total_steps=total_steps,
                            counts={**counts, "messages_imported": n},
                        ),
                    )
                else:
                    # amoCRM AJAX timeline/inbox is experimental and can hang
                    # per account. Keep core exports reliable; re-enable this
                    # only after adding bounded paging/time limits per scope.
                    messages_processed = 0
                    chats_processed = 0
                    messages_coverage = {
                        "messages_imported": 0,
                        "chats_seen": 0,
                        "chats_matched": 0,
                        "unmatched_chats": 0,
                        "skipped_reason": "timeline_messages_disabled",
                    }
                    logger.info(
                        "amocrm_timeline_messages_import_skipped",
                        extra={"schema": schema, "reason": "timeline_messages_disabled"},
                    )
                counts["chats"] = _tenant_table_count(sess, schema=schema, table="chats")
                counts["messages"] = _tenant_table_count(sess, schema=schema, table="messages")
                update_job_progress(
                    job_row_id,
                    stage="messages",
                    completed_steps=13,
                    total_steps=total_steps,
                    counts={
                        **counts,
                        "messages_processed": messages_processed,
                        "chats_processed": chats_processed,
                        "messages_chats_seen": int(messages_coverage.get("chats_seen", 0) or 0),
                        "messages_chats_matched": int(messages_coverage.get("chats_matched", 0) or 0),
                        "messages_unmatched_chats": int(messages_coverage.get("unmatched_chats", 0) or 0),
                    },
                )

                events_skipped_reason: str | None = None
                if since is None and not AMOCRM_FULL_EXPORT_EVENTS_ENABLED:
                    events_processed = 0
                    events_skipped_reason = "full_export_events_disabled"
                    logger.info(
                        "amocrm_full_export_events_import_skipped",
                        extra={"schema": schema, "reason": events_skipped_reason},
                    )
                else:
                    events_processed = _pull_events(
                        sess,
                        connector,
                        access_token,
                        since=since,
                        schema=schema,
                        progress=lambda n: update_job_progress(
                            job_row_id,
                            stage="events",
                            completed_steps=13,
                            total_steps=total_steps,
                            counts={**counts, "events_imported": n},
                        ),
                    )
                counts["events"] = _tenant_table_count(sess, schema=schema, table="raw_events")
                update_job_progress(
                    job_row_id,
                    stage="events",
                    completed_steps=14,
                    total_steps=total_steps,
                    counts={
                        **counts,
                        "events_processed": events_processed,
                        "events_skipped_reason": events_skipped_reason,
                    },
                )

                stage_transitions_processed = _pull_stage_transitions(
                    sess,
                    schema=schema,
                    deal_map=deal_map,
                    stage_map=stage_map,
                    user_map=user_map,
                )
                counts["stage_transitions"] = _tenant_table_count(
                    sess,
                    schema=schema,
                    table="deal_stage_transitions",
                )
                update_job_progress(
                    job_row_id,
                    stage="stage_transitions",
                    completed_steps=16,
                    total_steps=total_steps,
                    counts={
                        **counts,
                        "stage_transitions_processed": stage_transitions_processed,
                    },
                )

            counts = _tenant_active_export_counts(
                sess,
                schema=schema,
                created_from=created_from,
                created_to=created_to,
                pipeline_ids=selected_pipeline_ids,
            )
            print(
                f"[pull_amocrm_core] schema={schema} active_counts={counts}",
                flush=True,
            )

        # Обновляем метаданные CrmConnection.
        # Bug G (#52.3G): реальное имя колонки в БД — ``metadata`` (см.
        # ``CrmConnection.metadata_json = Column("metadata", JSONB, ...)``;
        # ORM-атрибут переименован, т.к. SQLAlchemy резервирует ``metadata``
        # у declarative base). Raw ``text()``-SQL обходит ORM-маппинг, поэтому
        # здесь используем реальное имя колонки — ``metadata``, а НЕ
        # ``metadata_json``. Регрессия покрыта в
        # ``tests/api/test_crm_pull_metadata_sql_column.py``.
        metadata_patch = {
            "last_pull_counts": counts,
            "last_pull_at": datetime.now(tz=timezone.utc).isoformat(),
            "active_export": _build_active_export_metadata(
                date_from_iso=effective_date_from_iso,
                date_to_iso=effective_date_to_iso,
                pipeline_ids=selected_pipeline_ids,
                counts=counts,
                messages_coverage=messages_coverage,
            ),
        }
        if auto_sync:
            metadata_patch["last_auto_sync_at"] = datetime.now(tz=timezone.utc).isoformat()

        with sync_session() as sess:
            sess.execute(
                text(
                    "UPDATE crm_connections SET "
                    "  last_sync_at = NOW(), "
                    "  updated_at = NOW(), "
                    "  metadata = COALESCE(metadata, '{}'::jsonb) "
                    "    || CAST(:patch AS JSONB) "
                    "WHERE id = CAST(:cid AS UUID)"
                ),
                {
                    "cid": connection_id,
                    "patch": json.dumps(metadata_patch, ensure_ascii=False),
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
            "auto_sync": auto_sync,
            "tenant_schema": schema,
            "counts": counts,
            "audit_job_enqueued": audit_enqueued,
        }
        charge_token_reservation_for_job(job_row_id, result)
        create_job_notification(
            job_row_id,
            kind="sync_complete",
            title=(
                "Автосинхронизация amoCRM завершена"
                if auto_sync
                else "Выгрузка amoCRM завершена"
            ),
            body=(
                f"Сделок: {counts.get('deals', 0)}, "
                f"контактов: {counts.get('contacts', 0)}, "
                f"компаний: {counts.get('companies', 0)}."
            ),
            metadata={"counts": counts, "auto_sync": auto_sync},
        )
        mark_job_succeeded(job_row_id, result)
        return result
    except Exception as exc:
        release_token_reservation_for_job(job_row_id, f"pull_amocrm_core: {exc}")
        mark_job_failed(job_row_id, f"pull_amocrm_core: {exc}")
        create_job_notification(
            job_row_id,
            kind="sync_failed",
            title="Синхронизация amoCRM не завершилась",
            body="Задача остановлена с ошибкой. Детали доступны в карточке подключения.",
            metadata={"auto_sync": auto_sync},
        )
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
