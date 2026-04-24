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
        "top_deals": [],
    }


def _dashboard_filters(
    conn: CrmConnection,
    *,
    deal_alias: str = "d",
    pipeline_alias: str = "p",
) -> tuple[str, dict[str, Any]]:
    active = _active_export(conn)
    clauses: list[str] = []
    params: dict[str, Any] = {}
    date_from = active.get("date_from")
    date_to = active.get("date_to")
    if date_from:
        clauses.append(f"{deal_alias}.created_at_external >= CAST(:active_date_from AS date)")
        params["active_date_from"] = _date_param(date_from)
    if date_to:
        clauses.append(
            f"{deal_alias}.created_at_external < CAST(:active_date_to AS date) + INTERVAL '1 day'"
        )
        params["active_date_to"] = _date_param(date_to)
    pipeline_ids = active.get("pipeline_ids")
    if isinstance(pipeline_ids, list) and pipeline_ids:
        placeholders: list[str] = []
        for idx, pipeline_id in enumerate(pipeline_ids):
            key = f"active_pipeline_{idx}"
            placeholders.append(f":{key}")
            params[key] = str(pipeline_id)
        clauses.append(f"{pipeline_alias}.external_id IN ({', '.join(placeholders)})")
    if not clauses:
        return "", params
    return "WHERE " + " AND ".join(clauses), params


def _dashboard_deal_join_filters(
    conn: CrmConnection,
    *,
    deal_alias: str = "d",
) -> tuple[str, dict[str, Any]]:
    active = _active_export(conn)
    clauses: list[str] = []
    params: dict[str, Any] = {}
    date_from = active.get("date_from")
    date_to = active.get("date_to")
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
        stage_where = ""
        stage_params: dict[str, Any] = {}
        if isinstance(pipeline_ids, list) and pipeline_ids:
            placeholders = []
            for idx, pipeline_id in enumerate(pipeline_ids):
                key = f"stage_pipeline_{idx}"
                placeholders.append(f":{key}")
                stage_params[key] = str(pipeline_id)
            stage_where = f"WHERE p.external_id IN ({', '.join(placeholders)})"
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
    # В tenant-схеме нет отдельного поля source — возвращаем mock всегда.
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
        rows = (
            await session.execute(
                text(
                    "SELECT c.channel, COUNT(m.id) "
                    "FROM chats c LEFT JOIN messages m ON m.chat_id = c.id "
                    "GROUP BY c.channel"
                )
            )
        ).all()
        by_channel = [{"channel": r[0] or "unknown", "count": r[1], "avg_response_min": 0} for r in rows]
        total = sum(b["count"] for b in by_channel)
        return {
            "mock": False,
            "connection_id": str(conn.id),
            "total": total,
            "by_channel": by_channel,
        }
    except Exception:
        return mock_dashboard_messages(str(conn.id))


@router.get("/crm/connections/{connection_id}/dashboard/sales")
async def dashboard_sales(
    connection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    conn = await _resolve_conn(session, user, connection_id)
    if _use_mock(conn):
        return _mock_sales_dashboard(str(conn.id))

    try:
        await _set_search_path(session, conn.tenant_schema)
        active = _active_export(conn)
        where_sql, params = _dashboard_filters(conn)
        deal_join_sql, deal_params = _dashboard_deal_join_filters(conn)
        monthly_where_sql = (
            f"{where_sql} AND d.created_at_external IS NOT NULL"
            if where_sql
            else "WHERE d.created_at_external IS NOT NULL"
        )
        pipeline_ids = active.get("pipeline_ids")
        stage_where = ""
        stage_params: dict[str, Any] = {}
        if isinstance(pipeline_ids, list) and pipeline_ids:
            placeholders: list[str] = []
            for idx, pipeline_id in enumerate(pipeline_ids):
                key = f"stage_pipeline_{idx}"
                placeholders.append(f":{key}")
                stage_params[key] = str(pipeline_id)
            stage_where = f"WHERE p.external_id IN ({', '.join(placeholders)})"

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
                    f"{where_sql} "
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

        return {
            "mock": False,
            "connection_id": str(conn.id),
            "filters": {
                "date_from": active.get("date_from"),
                "date_to": active.get("date_to"),
                "pipeline_ids": active.get("pipeline_ids") or [],
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
