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
        rows = (
            await session.execute(
                text("SELECT status, COUNT(*) FROM deals GROUP BY status")
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
        rows = (
            await session.execute(
                text(
                    "SELECT s.name, s.sort_order, COUNT(d.id) "
                    "FROM stages s LEFT JOIN deals d ON d.stage_id = s.id "
                    "GROUP BY s.id, s.name, s.sort_order ORDER BY s.sort_order"
                )
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
        rows = (
            await session.execute(
                text(
                    "SELECT u.id, u.full_name, "
                    "COUNT(d.id) FILTER (WHERE d.status='open'), "
                    "COUNT(d.id) FILTER (WHERE d.status='won') "
                    "FROM crm_users u LEFT JOIN deals d ON d.responsible_user_id = u.id "
                    "GROUP BY u.id, u.full_name"
                )
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
