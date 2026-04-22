"""AI endpoints — mock insights, knowledge-base, research-consent."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.db import get_session
from app.core.jobs import enqueue, queue_for_kind
from app.crm.mock_data import mock_behavior_patterns, mock_conversation_scores
from app.db.models import (
    AiBehaviorPattern,
    AiClientKnowledgeItem,
    AiConversationScore,
    AiResearchConsent,
    CrmConnection,
    Job,
    User,
    WorkspaceMember,
)
from packages_ai.mock_insights import build_mock_insights

router = APIRouter(tags=["ai"])


async def _resolve_conn(
    session: AsyncSession, user: User, connection_id: uuid.UUID
) -> CrmConnection:
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


@router.post("/crm/connections/{connection_id}/ai/analyze", status_code=status.HTTP_202_ACCEPTED)
async def ai_analyze(
    connection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    conn = await _resolve_conn(session, user, connection_id)
    # В stored payload кладём "mock": True как marker, worker получает
    # только connection_id (см. worker.jobs.ai.analyze_conversation signature).
    db_payload = {"connection_id": str(conn.id), "mock": True}
    worker_payload = {"connection_id": str(conn.id)}
    job = Job(
        workspace_id=conn.workspace_id,
        crm_connection_id=conn.id,
        kind="analyze_conversation",
        queue=queue_for_kind("analyze_conversation"),
        status="queued",
        payload=db_payload,
    )
    session.add(job)
    await session.flush()  # populates job.id (Task #52.6)
    rq_id = enqueue(
        "analyze_conversation", worker_payload, job_row_id=str(job.id)
    )
    job.rq_job_id = rq_id
    await session.commit()
    return {"job_id": str(job.id)}


@router.get("/crm/connections/{connection_id}/ai/insights")
async def ai_insights(
    connection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    conn = await _resolve_conn(session, user, connection_id)
    # Mock insights (детерминированные — см. packages/ai/mock_insights.py).
    return {
        "connection_id": str(conn.id),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "insights": build_mock_insights(connection_id=str(conn.id)),
        "mock": True,
    }


@router.get("/crm/connections/{connection_id}/knowledge-base")
async def ai_knowledge_base(
    connection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    conn = await _resolve_conn(session, user, connection_id)
    rows = (
        await session.execute(
            select(AiClientKnowledgeItem)
            .where(AiClientKnowledgeItem.workspace_id == conn.workspace_id)
            .where(AiClientKnowledgeItem.status == "active")
            .order_by(AiClientKnowledgeItem.created_at.desc())
        )
    ).scalars().all()
    if not rows:
        # Возвращаем 1 mock-item для демо.
        return [
            {
                "id": "mock-1",
                "source": "manual",
                "title": "Пример: возражение «Дорого»",
                "body": "Стандартный ответ: уточняем критерии выбора, предлагаем демо.",
                "mock": True,
            }
        ]
    return [
        {
            "id": str(r.id),
            "source": r.source,
            "title": r.title,
            "body": r.body,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.post("/crm/connections/{connection_id}/ai/research-consent")
async def ai_research_consent_accept(
    connection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    conn = await _resolve_conn(session, user, connection_id)
    consent = (
        await session.execute(
            select(AiResearchConsent).where(AiResearchConsent.workspace_id == conn.workspace_id)
        )
    ).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if not consent:
        consent = AiResearchConsent(
            workspace_id=conn.workspace_id,
            status="accepted",
            accepted_at=now,
            accepted_by_user_id=user.id,
            terms_version="v1",
        )
        session.add(consent)
    else:
        consent.status = "accepted"
        consent.accepted_at = now
        consent.accepted_by_user_id = user.id
        consent.revoked_at = None
        consent.terms_version = "v1"
    await session.commit()
    return {"status": consent.status, "accepted_at": now.isoformat()}


@router.delete("/crm/connections/{connection_id}/ai/research-consent")
async def ai_research_consent_revoke(
    connection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    conn = await _resolve_conn(session, user, connection_id)
    consent = (
        await session.execute(
            select(AiResearchConsent).where(AiResearchConsent.workspace_id == conn.workspace_id)
        )
    ).scalar_one_or_none()
    if not consent:
        return {"status": "not_asked"}
    now = datetime.now(timezone.utc)
    consent.status = "revoked"
    consent.revoked_at = now
    await session.commit()
    return {"status": "revoked", "revoked_at": now.isoformat()}


# -------------------- AI conversation scores --------------------

@router.get("/crm/connections/{connection_id}/ai/conversation-scores")
async def ai_conversation_scores(
    connection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """
    Список AI-оценок разговоров.
    Если в БД пусто — возвращаем mock-данные для UI.
    """
    conn = await _resolve_conn(session, user, connection_id)
    rows = (
        await session.execute(
            select(AiConversationScore)
            .where(AiConversationScore.workspace_id == conn.workspace_id)
            .order_by(AiConversationScore.created_at.desc())
            .limit(50)
        )
    ).scalars().all()
    if not rows:
        return {
            "connection_id": str(conn.id),
            "scores": mock_conversation_scores(str(conn.id)),
            "mock": True,
        }
    return {
        "connection_id": str(conn.id),
        "scores": [
            {
                "id": str(r.id),
                "overall_score": float(r.overall_score) if r.overall_score else None,
                "dimension_scores": r.dimension_scores,
                "confidence": float(r.confidence) if r.confidence else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
        "mock": False,
    }


# -------------------- AI behavior patterns --------------------

@router.get("/crm/connections/{connection_id}/ai/behavior-patterns")
async def ai_behavior_patterns(
    connection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Поведенческие паттерны менеджеров. Если нет данных — mock."""
    conn = await _resolve_conn(session, user, connection_id)
    rows = (
        await session.execute(
            select(AiBehaviorPattern)
            .where(AiBehaviorPattern.workspace_id == conn.workspace_id)
            .order_by(AiBehaviorPattern.created_at.desc())
            .limit(50)
        )
    ).scalars().all()
    if not rows:
        return {
            "connection_id": str(conn.id),
            "patterns": mock_behavior_patterns(str(conn.id)),
            "mock": True,
        }
    return {
        "connection_id": str(conn.id),
        "patterns": [
            {
                "id": str(r.id),
                "pattern_type": r.pattern_type,
                "frequency_bucket": r.frequency_bucket,
                "sample_size": r.sample_size,
                "description": r.description,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
        "mock": False,
    }
