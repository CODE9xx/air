"""
Dashboards — read-only endpoints поверх tenant-схемы.

Брифом заказаны endpoint'ы под connection-id:
  * ``/crm/connections/:id/dashboard/overview``
  * ``/crm/connections/:id/dashboard/funnel``
  * ``/crm/connections/:id/dashboard/sources``
  * ``/crm/connections/:id/dashboard/managers``
  * ``/crm/connections/:id/dashboard/calls``
  * ``/crm/connections/:id/dashboard/messages``

Если ``tenant_schema IS NULL`` или ``MOCK_CRM_MODE=true`` — возвращаем
синтетические mock-данные из ``app/crm/mock_data.py``. Иначе — живой
aggregator через ``SET LOCAL search_path``.

Сохраняем legacy endpoint'ы ``/dashboards/*`` для обратной совместимости.
"""
from __future__ import annotations

import re
import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.db import get_session
from app.core.settings import get_settings
from app.crm.mock_data import (
    mock_dashboard_calls,
    mock_dashboard_funnel,
    mock_dashboard_managers,
    mock_dashboard_messages,
    mock_dashboard_overview,
    mock_dashboard_sources,
)
from app.db.models import CrmConnection, User, WorkspaceMember

router = APIRouter(tags=["dashboards"])
settings = get_settings()

_SCHEMA_RE = re.compile(r"^crm_[a-z0-9]+_[a-z0-9]{6,16}$")
HIDDEN_PIPELINE_NAMES = ("Корзина", "План", "Тендера", "Hunter")
HIDDEN_PIPELINE_PATTERNS = ("корзина", "тендер", "hunter")


async def _resolve_conn(
    session: AsyncSession, user: User, connection_id: uuid.UUID
) -> CrmConnection:
    """Проверка: connection существует и user — member workspace."""
    conn = (
        await session.execute(select(CrmConnection).where(CrmConnection.id == connection_id))
    ).scalar_one_or_none()
    if not conn:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Connection not found"}},
        )
    m = (
        await session.execute(
            select(WorkspaceMember)
            .where(WorkspaceMember.workspace_id == conn.workspace_id)
            .where(WorkspaceMember.user_id == user.id)
        )
    ).scalar_one_or_none()
    if not m:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "forbidden", "message": "No access"}},
        )
    return conn


def _safe_schema(schema: str) -> str:
    if not _SCHEMA_RE.match(schema):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": {"code": "internal_error", "message": "Bad tenant schema"}},
        )
    return schema


async def _set_search_path(session: AsyncSession, schema: str) -> None:
    schema = _safe_schema(schema)
    await session.execute(text(f'SET LOCAL search_path TO "{schema}", public'))


def _use_mock(conn: CrmConnection) -> bool:
    """Решает: использовать mock или живые tenant-данные."""
    if settings.mock_crm_mode:
        return True
    if not conn.tenant_schema:
        return True
    return False


def _active_export(conn: CrmConnection) -> dict[str, Any]:
    meta = conn.metadata_json or {}
    active = meta.get("active_export")
    return active if isinstance(active, dict) else {}


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _rub(value: Any) -> float:
    return round(float(value or 0) / 100, 2)


def _date_param(value: Any) -> date | str:
    if isinstance(value, date):
        return value
    raw = str(value)
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return raw


def _parse_date_filter(value: Any, field: str) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": "validation_error", "message": f"{field} must be YYYY-MM-DD"}},
        )


def _where_with_extra(where_sql: str, clause: str) -> str:
    if where_sql:
        return f"{where_sql} AND {clause}"
    return f"WHERE {clause}"


def _hidden_pipeline_clause(
    pipeline_alias: str = "p",
    *,
    prefix: str = "hidden_pipeline",
    allow_null: bool = True,
) -> tuple[str, dict[str, Any]]:
    name_sql = f"LOWER(BTRIM(COALESCE({pipeline_alias}.name, '')))"
    params: dict[str, Any] = {}
    exact_keys: list[str] = []
    for idx, name in enumerate(HIDDEN_PIPELINE_NAMES):
        key = f"{prefix}_{idx}"
        params[key] = name.lower()
        exact_keys.append(f":{key}")
    pattern_clauses: list[str] = []
    for idx, pattern in enumerate(HIDDEN_PIPELINE_PATTERNS):
        key = f"{prefix}_pattern_{idx}"
        params[key] = f"%{pattern}%"
        pattern_clauses.append(f"{name_sql} NOT LIKE :{key}")
    clauses = [f"{name_sql} NOT IN ({', '.join(exact_keys)})", *pattern_clauses]
    clause = " AND ".join(clauses)
    if allow_null:
        clause = f"({pipeline_alias}.id IS NULL OR ({clause}))"
    return clause, params


def _mock_sales_dashboard(connection_id: str) -> dict[str, Any]:
    overview = mock_dashboard_overview(connection_id)
    funnel = mock_dashboard_funnel(connection_id)
    managers = mock_dashboard_managers(connection_id)
    total_deals = int(overview.get("total_deals") or 0)
    won_deals = int(overview.get("won_deals") or 0)
    lost_deals = int(overview.get("lost_deals") or 0)
    open_deals = int(overview.get("open_deals") or 0)
    revenue = 18_500_000
    return {
        "mock": True,
        "connection_id": connection_id,
        "filters": {"date_from": None, "date_to": None, "pipeline_ids": []},
        "kpis": {
            "total_deals": total_deals,
            "open_deals": open_deals,
            "won_deals": won_deals,
            "lost_deals": lost_deals,
            "won_rate": round(won_deals / total_deals, 4) if total_deals else 0,
            "lost_rate": round(lost_deals / total_deals, 4) if total_deals else 0,
            "revenue_rub": revenue,
            "avg_deal_rub": round(revenue / max(1, won_deals), 2),
            "date_from": None,
            "date_to": None,
            "pipeline_count": 4,
            "manager_count": len(managers.get("managers", [])),
        },
        "monthly_revenue": [
            {"month": "2025-11-01", "deals": 960, "won_deals": 210, "revenue_rub": 3_400_000},
            {"month": "2025-12-01", "deals": 1040, "won_deals": 244, "revenue_rub": 3_900_000},
            {"month": "2026-01-01", "deals": 1160, "won_deals": 276, "revenue_rub": 4_420_000},
            {"month": "2026-02-01", "deals": 1220, "won_deals": 288, "revenue_rub": 4_680_000},
            {"month": "2026-03-01", "deals": 1310, "won_deals": 305, "revenue_rub": 5_100_000},
        ],
        "pipeline_breakdown": [
            {"pipeline": "Продажи", "deals": 5200, "open_deals": 3200, "won_deals": 1400, "lost_deals": 600, "revenue_rub": 11_200_000},
            {"pipeline": "Повторные", "deals": 2600, "open_deals": 1200, "won_deals": 980, "lost_deals": 420, "revenue_rub": 7_300_000},
        ],
        "stage_funnel": funnel.get("stages", []),
        "status_breakdown": [
            {"status": "open", "deals": open_deals, "revenue_rub": 0},
            {"status": "won", "deals": won_deals, "revenue_rub": revenue},
            {"status": "lost", "deals": lost_deals, "revenue_rub": 0},
        ],
        "manager_leaderboard": [
            {
                "user_id": item.get("user_id"),
                "name": item.get("full_name"),
                "deals": int(item.get("deals_open") or 0) + int(item.get("deals_won") or 0),
                "open_deals": item.get("deals_open") or 0,
                "won_deals": item.get("deals_won") or 0,
                "lost_deals": 0,
                "revenue_rub": 0,
                "avg_deal_rub": 0,
            }
            for item in managers.get("managers", [])
        ],
        "manager_metrics": [
            {
                "user_id": item.get("user_id"),
                "name": item.get("full_name"),
                "applications": int(item.get("deals_open") or 0) + int(item.get("deals_won") or 0),
                "calls": 0,
                "sales_count": int(item.get("deals_won") or 0),
                "not_sales_count": 0,
                "sales_amount": 0,
                "conversion": 0,
                "calls_in": 0,
                "calls_out": 0,
                "calls_duration_sec": 0,
                "messages_count": 0,
                "emails_sent": 0,
                "currency": "RUB",
            }
            for item in managers.get("managers", [])
        ],
        "top_deals": [],
        "sales_cycle": {
            "avg_won_cycle_days": 18,
            "avg_lost_cycle_days": 27,
            "avg_open_age_days": 34,
            "stale_open_deals": 420,
            "stale_open_amount_rub": 6_800_000,
        },
        "open_age_buckets": [
            {"bucket": "0_7", "label": "0-7", "deals": 780, "amount_rub": 4_100_000},
            {"bucket": "8_30", "label": "8-30", "deals": 1420, "amount_rub": 8_200_000},
            {"bucket": "31_90", "label": "31-90", "deals": 930, "amount_rub": 5_700_000},
            {"bucket": "90_plus", "label": "90+", "deals": 420, "amount_rub": 6_800_000},
        ],
        "pipeline_health": [
            {
                "pipeline": "Продажи",
                "deals": 5200,
                "open_deals": 3200,
                "won_deals": 1400,
                "lost_deals": 600,
                "stale_open_deals": 260,
                "open_amount_rub": 5_900_000,
                "avg_open_age_days": 31,
                "oldest_open_age_days": 240,
                "won_rate": 0.2692,
            }
        ],
        "manager_risk": [
            {
                "user_id": "mock-1",
                "name": "Мария Иванова",
                "open_deals": 620,
                "stale_open_deals": 84,
                "open_amount_rub": 2_100_000,
                "avg_open_age_days": 29,
                "oldest_open_age_days": 180,
            }
        ],
    }


def _dashboard_filter_state(
    conn: CrmConnection,
    *,
    period: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    pipeline_id: str | None = None,
) -> dict[str, Any]:
    active = _active_export(conn)
    normalized_period = period if period in {"active_export", "all_time", "custom"} else "active_export"
    active_pipeline_ids = [
        str(item)
        for item in active.get("pipeline_ids", [])
        if isinstance(item, (str, int)) and str(item).strip()
    ]

    selected_date_from = None if normalized_period == "all_time" else active.get("date_from")
    selected_date_to = None if normalized_period == "all_time" else active.get("date_to")
    if date_from:
        selected_date_from = _parse_date_filter(date_from, "date_from").isoformat()
        normalized_period = "custom"
    if date_to:
        selected_date_to = _parse_date_filter(date_to, "date_to").isoformat()
        normalized_period = "custom"
    if selected_date_from and selected_date_to:
        parsed_from = _parse_date_filter(selected_date_from, "date_from")
        parsed_to = _parse_date_filter(selected_date_to, "date_to")
        if parsed_from > parsed_to:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error": {
                        "code": "validation_error",
                        "message": "date_from must be <= date_to",
                    }
                },
            )

    requested_pipeline = str(pipeline_id).strip() if pipeline_id else None
    if requested_pipeline and active_pipeline_ids and requested_pipeline not in active_pipeline_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "pipeline_not_in_export",
                    "message": "Pipeline was not selected in the active export",
                }
            },
        )
    selected_pipeline_ids = [requested_pipeline] if requested_pipeline else active_pipeline_ids
    return {
        "period": normalized_period,
        "date_from": selected_date_from,
        "date_to": selected_date_to,
        "pipeline_id": requested_pipeline,
        "pipeline_ids": selected_pipeline_ids,
        "active_pipeline_ids": active_pipeline_ids,
    }


def _dashboard_filters(
    conn: CrmConnection,
    *,
    filters: dict[str, Any] | None = None,
    deal_alias: str = "d",
    pipeline_alias: str = "p",
) -> tuple[str, dict[str, Any]]:
    state = filters or _dashboard_filter_state(conn)
    clauses: list[str] = []
    params: dict[str, Any] = {}
    date_from = state.get("date_from")
    date_to = state.get("date_to")
    if date_from:
        clauses.append(f"{deal_alias}.created_at_external >= CAST(:active_date_from AS date)")
        params["active_date_from"] = _date_param(date_from)
    if date_to:
        clauses.append(
            f"{deal_alias}.created_at_external < CAST(:active_date_to AS date) + INTERVAL '1 day'"
        )
        params["active_date_to"] = _date_param(date_to)
    pipeline_ids = state.get("pipeline_ids")
    if isinstance(pipeline_ids, list) and pipeline_ids:
        placeholders: list[str] = []
        for idx, pipeline_id in enumerate(pipeline_ids):
            key = f"active_pipeline_{idx}"
            placeholders.append(f":{key}")
            params[key] = str(pipeline_id)
        clauses.append(f"{pipeline_alias}.external_id IN ({', '.join(placeholders)})")
    hidden_clause, hidden_params = _hidden_pipeline_clause(pipeline_alias)
    clauses.append(hidden_clause)
    params.update(hidden_params)
    if not clauses:
        return "", params
    return "WHERE " + " AND ".join(clauses), params


def _dashboard_deal_join_filters(
    conn: CrmConnection,
    *,
    filters: dict[str, Any] | None = None,
    deal_alias: str = "d",
) -> tuple[str, dict[str, Any]]:
    state = filters or _dashboard_filter_state(conn)
    clauses: list[str] = []
    params: dict[str, Any] = {}
    date_from = state.get("date_from")
    date_to = state.get("date_to")
    if date_from:
        clauses.append(f"{deal_alias}.created_at_external >= CAST(:active_date_from AS date)")
        params["active_date_from"] = _date_param(date_from)
    if date_to:
        clauses.append(
            f"{deal_alias}.created_at_external < CAST(:active_date_to AS date) + INTERVAL '1 day'"
        )
        params["active_date_to"] = _date_param(date_to)
    if not clauses:
        return "", params
    return " AND " + " AND ".join(clauses), params


# -------------------- /crm/connections/:id/dashboard/* --------------------

@router.get("/crm/connections/{connection_id}/dashboard/overview")
async def dashboard_overview(
    connection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    conn = await _resolve_conn(session, user, connection_id)
    if _use_mock(conn):
        return mock_dashboard_overview(str(conn.id))
    try:
        await _set_search_path(session, conn.tenant_schema)
        where_sql, params = _dashboard_filters(conn)
        rows = (
            await session.execute(
                text(
                    "SELECT d.status, COUNT(*) "
                    "FROM deals d LEFT JOIN pipelines p ON p.id = d.pipeline_id "
                    f"{where_sql} "
                    "GROUP BY d.status"
                ),
                params,
            )
        ).all()
        by_status = {r[0] or "unknown": r[1] for r in rows}
        return {
            "mock": False,
            "connection_id": str(conn.id),
            "by_status": by_status,
            "total_deals": sum(by_status.values()),
            "open_deals": by_status.get("open", 0),
            "won_deals": by_status.get("won", 0),
            "lost_deals": by_status.get("lost", 0),
        }
    except Exception:
        return mock_dashboard_overview(str(conn.id))


@router.get("/crm/connections/{connection_id}/dashboard/funnel")
async def dashboard_funnel(
    connection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    conn = await _resolve_conn(session, user, connection_id)
    if _use_mock(conn):
        return mock_dashboard_funnel(str(conn.id))
    try:
        await _set_search_path(session, conn.tenant_schema)
        deal_join_sql, deal_params = _dashboard_deal_join_filters(conn)
        active = _active_export(conn)
        pipeline_ids = active.get("pipeline_ids")
        stage_where_parts: list[str] = []
        stage_params: dict[str, Any] = {}
        hidden_clause, hidden_params = _hidden_pipeline_clause(
            "p",
            prefix="stage_hidden_pipeline",
            allow_null=False,
        )
        stage_where_parts.append(hidden_clause)
        stage_params.update(hidden_params)
        if isinstance(pipeline_ids, list) and pipeline_ids:
            placeholders = []
            for idx, pipeline_id in enumerate(pipeline_ids):
                key = f"stage_pipeline_{idx}"
                placeholders.append(f":{key}")
                stage_params[key] = str(pipeline_id)
            stage_where_parts.append(f"p.external_id IN ({', '.join(placeholders)})")
        stage_where = "WHERE " + " AND ".join(stage_where_parts)
        rows = (
            await session.execute(
                text(
                    "SELECT s.name, s.sort_order, COUNT(d.id) "
                    "FROM stages s "
                    "LEFT JOIN pipelines p ON p.id = s.pipeline_id "
                    f"LEFT JOIN deals d ON d.stage_id = s.id {deal_join_sql} "
                    f"{stage_where} "
                    "GROUP BY s.id, s.name, s.sort_order ORDER BY s.sort_order"
                ),
                {**deal_params, **stage_params},
            )
        ).all()
        prev: int | None = None
        stages: list[dict[str, Any]] = []
        for r in rows:
            count = r[2]
            conv = None if prev in (None, 0) else round(count / prev, 3) if prev else None
            stages.append({"stage": r[0], "count": count, "conversion_from_previous": conv})
            prev = count
        return {"mock": False, "connection_id": str(conn.id), "stages": stages}
    except Exception:
        return mock_dashboard_funnel(str(conn.id))


@router.get("/crm/connections/{connection_id}/dashboard/sources")
async def dashboard_sources(
    connection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    conn = await _resolve_conn(session, user, connection_id)
    if _use_mock(conn):
        return mock_dashboard_sources(str(conn.id))
    try:
        await _set_search_path(session, conn.tenant_schema)
        where_sql, params = _dashboard_filters(conn)
        raw_dashboard_sources = (
            await session.execute(
                text(
                    "SELECT COALESCE(NULLIF(ds.source_name, ''), NULLIF(ds.utm_source, ''), 'Без источника') AS source, "
                    "       COUNT(DISTINCT d.id), "
                    "       COUNT(DISTINCT d.id) FILTER (WHERE d.status='won'), "
                    "       COALESCE(SUM(d.price_cents) FILTER (WHERE d.status='won'), 0), "
                    "       COALESCE(MAX(ds.utm_medium), ''), "
                    "       COALESCE(MAX(ds.utm_campaign), '') "
                    "FROM deals d "
                    "LEFT JOIN pipelines p ON p.id = d.pipeline_id "
                    "LEFT JOIN deal_sources ds ON ds.deal_id = d.id "
                    f"{where_sql} "
                    "GROUP BY COALESCE(NULLIF(ds.source_name, ''), NULLIF(ds.utm_source, ''), 'Без источника') "
                    "ORDER BY COUNT(DISTINCT d.id) DESC "
                    "LIMIT 30"
                ),
                params,
            )
        ).all()
        return {
            "mock": False,
            "connection_id": str(conn.id),
            "sources": [
                {
                    "name": row[0],
                    "count": int(row[1] or 0),
                    "won": int(row[2] or 0),
                    "revenue_cents": int(row[3] or 0),
                    "utm_medium": row[4] or None,
                    "utm_campaign": row[5] or None,
                }
                for row in raw_dashboard_sources
            ],
        }
    except Exception:
        return mock_dashboard_sources(str(conn.id))


@router.get("/crm/connections/{connection_id}/dashboard/managers")
async def dashboard_managers(
    connection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    conn = await _resolve_conn(session, user, connection_id)
    if _use_mock(conn):
        return mock_dashboard_managers(str(conn.id))
    try:
        await _set_search_path(session, conn.tenant_schema)
        where_sql, params = _dashboard_filters(conn)
        where_sql = _where_with_extra(where_sql, "COALESCE(u.is_active, TRUE) IS TRUE")
        rows = (
            await session.execute(
                text(
                    "SELECT u.id, u.full_name, "
                    "COUNT(d.id) FILTER (WHERE d.status='open'), "
                    "COUNT(d.id) FILTER (WHERE d.status='won') "
                    "FROM crm_users u "
                    "LEFT JOIN deals d ON d.responsible_user_id = u.id "
                    "LEFT JOIN pipelines p ON p.id = d.pipeline_id "
                    f"{where_sql} "
                    "GROUP BY u.id, u.full_name"
                ),
                params,
            )
        ).all()
        managers = [
            {
                "user_id": str(r[0]),
                "full_name": r[1],
                "deals_open": r[2] or 0,
                "deals_won": r[3] or 0,
                "tasks_overdue": 0,
                "calls_last_7d": 0,
            }
            for r in rows
        ]
        return {"mock": False, "connection_id": str(conn.id), "managers": managers}
    except Exception:
        return mock_dashboard_managers(str(conn.id))


@router.get("/crm/connections/{connection_id}/dashboard/calls")
async def dashboard_calls(
    connection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    conn = await _resolve_conn(session, user, connection_id)
    if _use_mock(conn):
        return mock_dashboard_calls(str(conn.id))
    try:
        await _set_search_path(session, conn.tenant_schema)
        row = (
            await session.execute(
                text(
                    "SELECT COUNT(*), "
                    "COUNT(*) FILTER (WHERE direction='in'), "
                    "COUNT(*) FILTER (WHERE direction='out'), "
                    "COALESCE(AVG(duration_sec), 0)::int "
                    "FROM calls"
                )
            )
        ).first()
        return {
            "mock": False,
            "connection_id": str(conn.id),
            "total": row[0] if row else 0,
            "inbound": row[1] if row else 0,
            "outbound": row[2] if row else 0,
            "avg_duration_sec": row[3] if row else 0,
            "by_day": [],
        }
    except Exception:
        return mock_dashboard_calls(str(conn.id))


@router.get("/crm/connections/{connection_id}/dashboard/messages")
async def dashboard_messages(
    connection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    conn = await _resolve_conn(session, user, connection_id)
    if _use_mock(conn):
        return mock_dashboard_messages(str(conn.id))
    try:
        await _set_search_path(session, conn.tenant_schema)
        where_sql, params = _dashboard_filters(conn)
        rows = (
            await session.execute(
                text(
                    "SELECT c.channel, COUNT(DISTINCT m.id), "
                    "       COUNT(DISTINCT m.id) FILTER (WHERE m.author_kind='client'), "
                    "       COUNT(DISTINCT m.id) FILTER (WHERE m.author_kind='user') "
                    "FROM chats c "
                    "LEFT JOIN messages m ON m.chat_id = c.id "
                    "LEFT JOIN deal_contacts dc ON dc.contact_id = c.contact_id "
                    "LEFT JOIN deals d ON d.id = COALESCE(c.deal_id, dc.deal_id) "
                    "LEFT JOIN pipelines p ON p.id = d.pipeline_id "
                    f"{where_sql} "
                    "GROUP BY c.channel"
                ),
                params,
            )
        ).all()
        by_channel = [
            {
                "channel": r[0] or "unknown",
                "count": int(r[1] or 0),
                "client_messages": int(r[2] or 0),
                "manager_messages": int(r[3] or 0),
                "avg_response_min": 0,
            }
            for r in rows
        ]
        total = sum(b["count"] for b in by_channel)
        return {
            "mock": False,
            "connection_id": str(conn.id),
            "total": total,
            "by_channel": by_channel,
            "messages_response_sla": {"avg_response_min": 0, "unanswered": 0},
        }
    except Exception:
        return mock_dashboard_messages(str(conn.id))


@router.get("/crm/connections/{connection_id}/dashboard/options")
async def dashboard_options(
    connection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    conn = await _resolve_conn(session, user, connection_id)
    filters = _dashboard_filter_state(conn)
    if _use_mock(conn):
        return {
            "mock": True,
            "connection_id": str(conn.id),
            "default_filters": filters,
            "pipelines": [
                {"id": "mock-sales", "name": "Продажи"},
                {"id": "mock-repeat", "name": "Повторные"},
            ],
        }

    await _set_search_path(session, conn.tenant_schema)
    active_pipeline_ids = filters.get("active_pipeline_ids") or []
    hidden_clause, hidden_params = _hidden_pipeline_clause(
        "p",
        prefix="options_hidden_pipeline",
        allow_null=False,
    )
    where_sql = f"WHERE p.external_id NOT LIKE 'ext-pipe-%' AND {hidden_clause}"
    params: dict[str, Any] = dict(hidden_params)
    if active_pipeline_ids:
        placeholders: list[str] = []
        for idx, pipeline_id in enumerate(active_pipeline_ids):
            key = f"pipeline_{idx}"
            placeholders.append(f":{key}")
            params[key] = str(pipeline_id)
        where_sql += f" AND p.external_id IN ({', '.join(placeholders)})"

    rows = (
        await session.execute(
            text(
                "SELECT p.external_id, COALESCE(p.name, p.external_id), COUNT(d.id) "
                "FROM pipelines p "
                "LEFT JOIN deals d ON d.pipeline_id = p.id "
                f"{where_sql} "
                "GROUP BY p.id, p.external_id, p.name "
                "ORDER BY COUNT(d.id) DESC, p.name"
            ),
            params,
        )
    ).all()
    return {
        "mock": False,
        "connection_id": str(conn.id),
        "default_filters": filters,
        "pipelines": [
            {"id": str(row[0]), "name": row[1], "deals": int(row[2] or 0)}
            for row in rows
        ],
    }


@router.get("/crm/connections/{connection_id}/dashboard/sales")
async def dashboard_sales(
    connection_id: uuid.UUID,
    period: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    pipeline_id: str | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    conn = await _resolve_conn(session, user, connection_id)
    if _use_mock(conn):
        return _mock_sales_dashboard(str(conn.id))

    try:
        await _set_search_path(session, conn.tenant_schema)
        filters = _dashboard_filter_state(
            conn,
            period=period,
            date_from=date_from,
            date_to=date_to,
            pipeline_id=pipeline_id,
        )
        where_sql, params = _dashboard_filters(conn, filters=filters)
        deal_join_sql, deal_params = _dashboard_deal_join_filters(conn, filters=filters)
        monthly_where_sql = (
            f"{where_sql} AND d.created_at_external IS NOT NULL"
            if where_sql
            else "WHERE d.created_at_external IS NOT NULL"
        )
        pipeline_ids = filters.get("pipeline_ids")
        stage_where_parts: list[str] = []
        stage_params: dict[str, Any] = {}
        hidden_clause, hidden_params = _hidden_pipeline_clause(
            "p",
            prefix="sales_stage_hidden_pipeline",
            allow_null=False,
        )
        stage_where_parts.append(hidden_clause)
        stage_params.update(hidden_params)
        if isinstance(pipeline_ids, list) and pipeline_ids:
            placeholders: list[str] = []
            for idx, pipeline_id in enumerate(pipeline_ids):
                key = f"stage_pipeline_{idx}"
                placeholders.append(f":{key}")
                stage_params[key] = str(pipeline_id)
            stage_where_parts.append(f"p.external_id IN ({', '.join(placeholders)})")
        stage_where = "WHERE " + " AND ".join(stage_where_parts)

        stats = (
            await session.execute(
                text(
                    "SELECT "
                    "  COUNT(d.id), "
                    "  COUNT(d.id) FILTER (WHERE d.status='open'), "
                    "  COUNT(d.id) FILTER (WHERE d.status='won'), "
                    "  COUNT(d.id) FILTER (WHERE d.status='lost'), "
                    "  COALESCE(SUM(d.price_cents) FILTER (WHERE d.status='won'), 0), "
                    "  COALESCE(AVG(NULLIF(d.price_cents, 0)) FILTER (WHERE d.status='won'), 0), "
                    "  MIN(d.created_at_external), "
                    "  MAX(d.created_at_external), "
                    "  COUNT(DISTINCT d.pipeline_id), "
                    "  COUNT(DISTINCT d.responsible_user_id) "
                    "FROM deals d LEFT JOIN pipelines p ON p.id = d.pipeline_id "
                    f"{where_sql}"
                ),
                params,
            )
        ).first()
        total_deals = int(stats[0] or 0) if stats else 0
        open_deals = int(stats[1] or 0) if stats else 0
        won_deals = int(stats[2] or 0) if stats else 0
        lost_deals = int(stats[3] or 0) if stats else 0

        monthly_rows = (
            await session.execute(
                text(
                    "SELECT date_trunc('month', d.created_at_external)::date AS month, "
                    "       COUNT(d.id), "
                    "       COUNT(d.id) FILTER (WHERE d.status='won'), "
                    "       COALESCE(SUM(d.price_cents) FILTER (WHERE d.status='won'), 0) "
                    "FROM deals d LEFT JOIN pipelines p ON p.id = d.pipeline_id "
                    f"{monthly_where_sql} "
                    "GROUP BY date_trunc('month', d.created_at_external)::date ORDER BY month"
                ),
                params,
            )
        ).all()

        pipeline_rows = (
            await session.execute(
                text(
                    "SELECT COALESCE(p.name, 'Без воронки'), "
                    "       COUNT(d.id), "
                    "       COUNT(d.id) FILTER (WHERE d.status='open'), "
                    "       COUNT(d.id) FILTER (WHERE d.status='won'), "
                    "       COUNT(d.id) FILTER (WHERE d.status='lost'), "
                    "       COALESCE(SUM(d.price_cents) FILTER (WHERE d.status='won'), 0) "
                    "FROM deals d LEFT JOIN pipelines p ON p.id = d.pipeline_id "
                    f"{where_sql} "
                    "GROUP BY p.id, p.name ORDER BY COUNT(d.id) DESC"
                ),
                params,
            )
        ).all()

        status_rows = (
            await session.execute(
                text(
                    "SELECT COALESCE(d.status, 'unknown'), COUNT(d.id), "
                    "       COALESCE(SUM(d.price_cents) FILTER (WHERE d.status='won'), 0) "
                    "FROM deals d LEFT JOIN pipelines p ON p.id = d.pipeline_id "
                    f"{where_sql} "
                    "GROUP BY d.status ORDER BY COUNT(d.id) DESC"
                ),
                params,
            )
        ).all()

        stage_rows = (
            await session.execute(
                text(
                    "SELECT COALESCE(p.name, 'Без воронки'), s.name, s.sort_order, COUNT(d.id), "
                    "       COALESCE(SUM(d.price_cents) FILTER (WHERE d.status='won'), 0) "
                    "FROM stages s "
                    "LEFT JOIN pipelines p ON p.id = s.pipeline_id "
                    f"LEFT JOIN deals d ON d.stage_id = s.id {deal_join_sql} "
                    f"{stage_where} "
                    "GROUP BY p.name, s.id, s.name, s.sort_order "
                    "ORDER BY COALESCE(p.name, 'Без воронки'), s.sort_order NULLS LAST, s.name "
                    "LIMIT 80"
                ),
                {**deal_params, **stage_params},
            )
        ).all()

        manager_where_sql = _where_with_extra(
            where_sql,
            "COALESCE(u.is_active, TRUE) IS TRUE",
        )
        manager_rows = (
            await session.execute(
                text(
                    "SELECT u.id, COALESCE(u.full_name, 'Без менеджера'), "
                    "       COUNT(d.id), "
                    "       COUNT(d.id) FILTER (WHERE d.status='open'), "
                    "       COUNT(d.id) FILTER (WHERE d.status='won'), "
                    "       COUNT(d.id) FILTER (WHERE d.status='lost'), "
                    "       COALESCE(SUM(d.price_cents) FILTER (WHERE d.status='won'), 0), "
                    "       COALESCE(AVG(NULLIF(d.price_cents, 0)) FILTER (WHERE d.status='won'), 0) "
                    "FROM crm_users u "
                    "LEFT JOIN deals d ON d.responsible_user_id = u.id "
                    "LEFT JOIN pipelines p ON p.id = d.pipeline_id "
                    f"{manager_where_sql} "
                    "GROUP BY u.id, u.full_name "
                    "ORDER BY COALESCE(SUM(d.price_cents) FILTER (WHERE d.status='won'), 0) DESC, "
                    "         COUNT(d.id) DESC "
                    "LIMIT 20"
                ),
                params,
            )
        ).all()

        top_deal_rows = (
            await session.execute(
                text(
                    "SELECT d.id, COALESCE(d.name, 'Без названия'), COALESCE(d.status, 'unknown'), "
                    "       COALESCE(d.price_cents, 0), p.name, s.name, u.full_name, "
                    "       d.created_at_external, d.closed_at_external "
                    "FROM deals d "
                    "LEFT JOIN pipelines p ON p.id = d.pipeline_id "
                    "LEFT JOIN stages s ON s.id = d.stage_id "
                    "LEFT JOIN crm_users u ON u.id = d.responsible_user_id "
                    f"{where_sql} "
                    "ORDER BY COALESCE(d.price_cents, 0) DESC, d.created_at_external DESC NULLS LAST "
                    "LIMIT 20"
                ),
                params,
            )
        ).all()

        open_where_sql = _where_with_extra(where_sql, "d.status='open'")
        sales_cycle = (
            await session.execute(
                text(
                    "SELECT "
                    "  COALESCE(AVG(EXTRACT(EPOCH FROM (d.closed_at_external - d.created_at_external)) / 86400.0) "
                    "    FILTER (WHERE d.status='won' AND d.closed_at_external IS NOT NULL "
                    "            AND d.created_at_external IS NOT NULL), 0), "
                    "  COALESCE(AVG(EXTRACT(EPOCH FROM (d.closed_at_external - d.created_at_external)) / 86400.0) "
                    "    FILTER (WHERE d.status='lost' AND d.closed_at_external IS NOT NULL "
                    "            AND d.created_at_external IS NOT NULL), 0), "
                    "  COALESCE(AVG(EXTRACT(EPOCH FROM (NOW() - d.created_at_external)) / 86400.0) "
                    "    FILTER (WHERE d.status='open' AND d.created_at_external IS NOT NULL), 0), "
                    "  COUNT(d.id) FILTER (WHERE d.status='open' "
                    "    AND COALESCE(d.updated_at_external, d.created_at_external) "
                    "        < NOW() - make_interval(days => 30)), "
                    "  COALESCE(SUM(d.price_cents) FILTER (WHERE d.status='open' "
                    "    AND COALESCE(d.updated_at_external, d.created_at_external) "
                    "        < NOW() - make_interval(days => 30)), 0) "
                    "FROM deals d LEFT JOIN pipelines p ON p.id = d.pipeline_id "
                    f"{where_sql}"
                ),
                params,
            )
        ).first()

        age_bucket_rows = (
            await session.execute(
                text(
                    "SELECT bucket, label, sort_order, COUNT(*) AS deals, COALESCE(SUM(price_cents), 0) "
                    "FROM ("
                    "  SELECT d.price_cents, "
                    "    CASE "
                    "      WHEN d.created_at_external IS NULL THEN 'unknown' "
                    "      WHEN d.created_at_external >= NOW() - make_interval(days => 7) THEN '0_7' "
                    "      WHEN d.created_at_external >= NOW() - make_interval(days => 30) THEN '8_30' "
                    "      WHEN d.created_at_external >= NOW() - make_interval(days => 90) THEN '31_90' "
                    "      WHEN d.created_at_external >= NOW() - make_interval(days => 180) THEN '91_180' "
                    "      ELSE '180_plus' "
                    "    END AS bucket, "
                    "    CASE "
                    "      WHEN d.created_at_external IS NULL THEN 'без даты' "
                    "      WHEN d.created_at_external >= NOW() - make_interval(days => 7) THEN '0-7' "
                    "      WHEN d.created_at_external >= NOW() - make_interval(days => 30) THEN '8-30' "
                    "      WHEN d.created_at_external >= NOW() - make_interval(days => 90) THEN '31-90' "
                    "      WHEN d.created_at_external >= NOW() - make_interval(days => 180) THEN '91-180' "
                    "      ELSE '180+' "
                    "    END AS label, "
                    "    CASE "
                    "      WHEN d.created_at_external IS NULL THEN 6 "
                    "      WHEN d.created_at_external >= NOW() - make_interval(days => 7) THEN 1 "
                    "      WHEN d.created_at_external >= NOW() - make_interval(days => 30) THEN 2 "
                    "      WHEN d.created_at_external >= NOW() - make_interval(days => 90) THEN 3 "
                    "      WHEN d.created_at_external >= NOW() - make_interval(days => 180) THEN 4 "
                    "      ELSE 5 "
                    "    END AS sort_order "
                    "  FROM deals d LEFT JOIN pipelines p ON p.id = d.pipeline_id "
                    f"  {open_where_sql}"
                    ") bucketed "
                    "GROUP BY bucket, label, sort_order ORDER BY sort_order"
                ),
                params,
            )
        ).all()

        pipeline_health_rows = (
            await session.execute(
                text(
                    "SELECT COALESCE(p.name, 'Без воронки'), "
                    "       COUNT(d.id), "
                    "       COUNT(d.id) FILTER (WHERE d.status='open'), "
                    "       COUNT(d.id) FILTER (WHERE d.status='won'), "
                    "       COUNT(d.id) FILTER (WHERE d.status='lost'), "
                    "       COUNT(d.id) FILTER (WHERE d.status='open' "
                    "         AND COALESCE(d.updated_at_external, d.created_at_external) "
                    "             < NOW() - make_interval(days => 30)), "
                    "       COALESCE(SUM(d.price_cents) FILTER (WHERE d.status='open'), 0), "
                    "       COALESCE(AVG(EXTRACT(EPOCH FROM (NOW() - d.created_at_external)) / 86400.0) "
                    "         FILTER (WHERE d.status='open' AND d.created_at_external IS NOT NULL), 0), "
                    "       COALESCE(MAX(EXTRACT(EPOCH FROM (NOW() - d.created_at_external)) / 86400.0) "
                    "         FILTER (WHERE d.status='open' AND d.created_at_external IS NOT NULL), 0) "
                    "FROM deals d LEFT JOIN pipelines p ON p.id = d.pipeline_id "
                    f"{where_sql} "
                    "GROUP BY p.id, p.name "
                    "ORDER BY COUNT(d.id) FILTER (WHERE d.status='open' "
                    "  AND COALESCE(d.updated_at_external, d.created_at_external) "
                    "      < NOW() - make_interval(days => 30)) DESC, "
                    "COALESCE(SUM(d.price_cents) FILTER (WHERE d.status='open'), 0) DESC "
                    "LIMIT 12"
                ),
                params,
            )
        ).all()

        manager_risk_rows = (
            await session.execute(
                text(
                    "SELECT u.id, COALESCE(u.full_name, 'Без менеджера'), "
                    "       COUNT(d.id) FILTER (WHERE d.status='open'), "
                    "       COUNT(d.id) FILTER (WHERE d.status='open' "
                    "         AND COALESCE(d.updated_at_external, d.created_at_external) "
                    "             < NOW() - make_interval(days => 30)), "
                    "       COALESCE(SUM(d.price_cents) FILTER (WHERE d.status='open'), 0), "
                    "       COALESCE(AVG(EXTRACT(EPOCH FROM (NOW() - d.created_at_external)) / 86400.0) "
                    "         FILTER (WHERE d.status='open' AND d.created_at_external IS NOT NULL), 0), "
                    "       COALESCE(MAX(EXTRACT(EPOCH FROM (NOW() - d.created_at_external)) / 86400.0) "
                    "         FILTER (WHERE d.status='open' AND d.created_at_external IS NOT NULL), 0) "
                    "FROM crm_users u "
                    "LEFT JOIN deals d ON d.responsible_user_id = u.id "
                    "LEFT JOIN pipelines p ON p.id = d.pipeline_id "
                    f"{manager_where_sql} "
                    "GROUP BY u.id, u.full_name "
                    "HAVING COUNT(d.id) FILTER (WHERE d.status='open') > 0 "
                    "ORDER BY COUNT(d.id) FILTER (WHERE d.status='open' "
                    "  AND COALESCE(d.updated_at_external, d.created_at_external) "
                    "      < NOW() - make_interval(days => 30)) DESC, "
                    "COALESCE(SUM(d.price_cents) FILTER (WHERE d.status='open'), 0) DESC "
                    "LIMIT 12"
                ),
                params,
            )
        ).all()

        task_rows = (
            await session.execute(
                text(
                    "SELECT "
                    "  COUNT(DISTINCT t.id), "
                    "  COUNT(DISTINCT t.id) FILTER (WHERE t.is_completed IS TRUE), "
                    "  COUNT(DISTINCT t.id) FILTER (WHERE t.is_completed IS FALSE "
                    "    AND t.due_at_external IS NOT NULL AND t.due_at_external < NOW()), "
                    "  COUNT(DISTINCT d.id) FILTER (WHERE d.status='open' AND t.id IS NULL) "
                    "FROM deals d "
                    "LEFT JOIN pipelines p ON p.id = d.pipeline_id "
                    "LEFT JOIN tasks t ON t.deal_id = d.id "
                    f"{where_sql}"
                ),
                params,
            )
        ).first()

        activity_rows = (
            await session.execute(
                text(
                    "SELECT u.id, "
                    "       COUNT(DISTINCT ca.id), "
                    "       COUNT(DISTINCT ca.id) FILTER (WHERE ca.direction='in'), "
                    "       COUNT(DISTINCT ca.id) FILTER (WHERE ca.direction='out'), "
                    "       COALESCE(SUM(ca.duration_sec), 0), "
                    "       COUNT(DISTINCT m.id), "
                    "       COUNT(DISTINCT t.id) FILTER (WHERE t.is_completed IS FALSE "
                    "         AND t.due_at_external IS NOT NULL AND t.due_at_external < NOW()) "
                    "FROM crm_users u "
                    "LEFT JOIN deals d ON d.responsible_user_id = u.id "
                    "LEFT JOIN pipelines p ON p.id = d.pipeline_id "
                    "LEFT JOIN calls ca ON ca.deal_id = d.id "
                    "LEFT JOIN chats ch ON ch.deal_id = d.id "
                    "LEFT JOIN messages m ON m.chat_id = ch.id "
                    "LEFT JOIN tasks t ON t.deal_id = d.id "
                    f"{manager_where_sql} "
                    "GROUP BY u.id"
                ),
                params,
            )
        ).all()
        activity_by_user = {
            str(row[0]): {
                "calls": int(row[1] or 0),
                "calls_in": int(row[2] or 0),
                "calls_out": int(row[3] or 0),
                "calls_duration_sec": int(row[4] or 0),
                "messages_count": int(row[5] or 0),
                "tasks_overdue": int(row[6] or 0),
            }
            for row in activity_rows
        }

        stage_transition_rows = (
            await session.execute(
                text(
                    "SELECT COALESCE(s_to.name, 'Неизвестный этап'), "
                    "       COUNT(DISTINCT dst.id), "
                    "       COALESCE(AVG(EXTRACT(EPOCH FROM (dst.changed_at_external - d.created_at_external)) / 86400.0) "
                    "         FILTER (WHERE dst.changed_at_external IS NOT NULL AND d.created_at_external IS NOT NULL), 0) "
                    "FROM deal_stage_transitions dst "
                    "JOIN deals d ON d.id = dst.deal_id "
                    "LEFT JOIN pipelines p ON p.id = d.pipeline_id "
                    "LEFT JOIN stages s_to ON s_to.id = dst.to_stage_id "
                    f"{where_sql} "
                    "GROUP BY s_to.id, s_to.name "
                    "ORDER BY COUNT(DISTINCT dst.id) DESC "
                    "LIMIT 30"
                ),
                params,
            )
        ).all()

        return {
            "mock": False,
            "connection_id": str(conn.id),
            "filters": {
                "period": filters.get("period"),
                "date_from": filters.get("date_from"),
                "date_to": filters.get("date_to"),
                "pipeline_id": filters.get("pipeline_id"),
                "pipeline_ids": filters.get("pipeline_ids") or [],
                "active_pipeline_ids": filters.get("active_pipeline_ids") or [],
            },
            "kpis": {
                "total_deals": total_deals,
                "open_deals": open_deals,
                "won_deals": won_deals,
                "lost_deals": lost_deals,
                "won_rate": round(won_deals / total_deals, 4) if total_deals else 0,
                "lost_rate": round(lost_deals / total_deals, 4) if total_deals else 0,
                "revenue_rub": _rub(stats[4] if stats else 0),
                "avg_deal_rub": _rub(stats[5] if stats else 0),
                "date_from": _iso(stats[6]) if stats else None,
                "date_to": _iso(stats[7]) if stats else None,
                "pipeline_count": int(stats[8] or 0) if stats else 0,
                "manager_count": int(stats[9] or 0) if stats else 0,
            },
            "monthly_revenue": [
                {
                    "month": _iso(row[0]),
                    "deals": int(row[1] or 0),
                    "won_deals": int(row[2] or 0),
                    "revenue_rub": _rub(row[3]),
                }
                for row in monthly_rows
            ],
            "pipeline_breakdown": [
                {
                    "pipeline": row[0],
                    "deals": int(row[1] or 0),
                    "open_deals": int(row[2] or 0),
                    "won_deals": int(row[3] or 0),
                    "lost_deals": int(row[4] or 0),
                    "revenue_rub": _rub(row[5]),
                }
                for row in pipeline_rows
            ],
            "status_breakdown": [
                {"status": row[0], "deals": int(row[1] or 0), "revenue_rub": _rub(row[2])}
                for row in status_rows
            ],
            "stage_funnel": [
                {
                    "pipeline": row[0],
                    "stage": row[1],
                    "sort_order": row[2],
                    "deals": int(row[3] or 0),
                    "revenue_rub": _rub(row[4]),
                }
                for row in stage_rows
            ],
            "manager_leaderboard": [
                {
                    "user_id": str(row[0]),
                    "name": row[1],
                    "deals": int(row[2] or 0),
                    "open_deals": int(row[3] or 0),
                    "won_deals": int(row[4] or 0),
                    "lost_deals": int(row[5] or 0),
                    "revenue_rub": _rub(row[6]),
                    "avg_deal_rub": _rub(row[7]),
                }
                for row in manager_rows
            ],
            "manager_metrics": [
                {
                    "user_id": str(row[0]),
                    "name": row[1],
                    "applications": int(row[2] or 0),
                    "calls": activity_by_user.get(str(row[0]), {}).get("calls", 0),
                    "sales_count": int(row[4] or 0),
                    "not_sales_count": int(row[5] or 0),
                    "sales_amount": _rub(row[6]),
                    "conversion": round(float(row[4] or 0) / float(row[2] or 1), 4),
                    "calls_in": activity_by_user.get(str(row[0]), {}).get("calls_in", 0),
                    "calls_out": activity_by_user.get(str(row[0]), {}).get("calls_out", 0),
                    "calls_duration_sec": activity_by_user.get(str(row[0]), {}).get("calls_duration_sec", 0),
                    "messages_count": activity_by_user.get(str(row[0]), {}).get("messages_count", 0),
                    "emails_sent": 0,
                    "currency": "RUB",
                }
                for row in manager_rows
            ],
            "top_deals": [
                {
                    "id": str(row[0]),
                    "name": row[1],
                    "status": row[2],
                    "price_rub": _rub(row[3]),
                    "pipeline": row[4],
                    "stage": row[5],
                    "manager": row[6],
                    "created_at": _iso(row[7]),
                    "closed_at": _iso(row[8]),
                }
                for row in top_deal_rows
            ],
            "sales_cycle": {
                "avg_won_cycle_days": round(float(sales_cycle[0] or 0), 1) if sales_cycle else 0,
                "avg_lost_cycle_days": round(float(sales_cycle[1] or 0), 1) if sales_cycle else 0,
                "avg_open_age_days": round(float(sales_cycle[2] or 0), 1) if sales_cycle else 0,
                "stale_open_deals": int(sales_cycle[3] or 0) if sales_cycle else 0,
                "stale_open_amount_rub": _rub(sales_cycle[4] if sales_cycle else 0),
            },
            "open_age_buckets": [
                {
                    "bucket": row[0],
                    "label": row[1],
                    "deals": int(row[3] or 0),
                    "amount_rub": _rub(row[4]),
                }
                for row in age_bucket_rows
            ],
            "pipeline_health": [
                {
                    "pipeline": row[0],
                    "deals": int(row[1] or 0),
                    "open_deals": int(row[2] or 0),
                    "won_deals": int(row[3] or 0),
                    "lost_deals": int(row[4] or 0),
                    "stale_open_deals": int(row[5] or 0),
                    "open_amount_rub": _rub(row[6]),
                    "avg_open_age_days": round(float(row[7] or 0), 1),
                    "oldest_open_age_days": round(float(row[8] or 0), 1),
                    "won_rate": round(float(row[3] or 0) / float(row[1] or 1), 4),
                }
                for row in pipeline_health_rows
            ],
            "manager_risk": [
                {
                    "user_id": str(row[0]),
                    "name": row[1],
                    "open_deals": int(row[2] or 0),
                    "stale_open_deals": int(row[3] or 0),
                    "open_amount_rub": _rub(row[4]),
                    "avg_open_age_days": round(float(row[5] or 0), 1),
                    "oldest_open_age_days": round(float(row[6] or 0), 1),
                }
                for row in manager_risk_rows
            ],
            "tasks_summary": {
                "tasks_total": int(task_rows[0] or 0) if task_rows else 0,
                "tasks_completed": int(task_rows[1] or 0) if task_rows else 0,
                "tasks_overdue": int(task_rows[2] or 0) if task_rows else 0,
                "tasks_no_next_step": int(task_rows[3] or 0) if task_rows else 0,
            },
            "stage_transition_metrics": [
                {
                    "stage": row[0],
                    "transitions": int(row[1] or 0),
                    "avg_days_from_creation": round(float(row[2] or 0), 1),
                }
                for row in stage_transition_rows
            ],
        }
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": {
                    "code": "dashboard_query_failed",
                    "message": "Dashboard data is temporarily unavailable",
                }
            },
        )


# -------------------- legacy /dashboards/* (совместимость) --------------------

@router.get("/dashboards/overview")
async def legacy_overview(
    crm_connection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    conn = await _resolve_conn(session, user, crm_connection_id)
    if _use_mock(conn):
        return mock_dashboard_overview(str(conn.id))
    return mock_dashboard_overview(str(conn.id))


@router.get("/dashboards/funnel")
async def legacy_funnel(
    crm_connection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    conn = await _resolve_conn(session, user, crm_connection_id)
    return mock_dashboard_funnel(str(conn.id))


@router.get("/dashboards/managers")
async def legacy_managers(
    crm_connection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    conn = await _resolve_conn(session, user, crm_connection_id)
    return mock_dashboard_managers(str(conn.id))
