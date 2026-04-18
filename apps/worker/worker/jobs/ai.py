"""
AI mock jobs (MVP):
- analyze_deals / analyze_calls / analyze_chats — генерят 3 mock insights в
  ai_conversation_scores / ai_behavior_patterns / ai_client_knowledge_items.
- analyze_conversation — единый алиас (роутится по kind).
- extract_patterns — генерит ai_behavior_patterns.
- anonymize_patterns — проверяет блэклист → privacy_risk → should_store.
- update_research_dataset — добавляет агрегированный паттерн в ai_research_patterns.

Без реальных LLM-вызовов.
"""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text

from ..lib.db import sync_session
from ._common import mark_job_failed, mark_job_running, mark_job_succeeded


# PII-блэклист — упрощённый MVP-набор. Полная версия — в docs/ai/ANONYMIZER_RULES.md.
_BLACKLIST_PATTERNS = [
    re.compile(r"\+?\d[\d\s\-\(\)]{8,}\d"),                     # телефон
    re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"),  # email
    re.compile(r"\b\d{16}\b"),                                  # длинная цифровая последовательность (карта)
    re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),                 # IP
]

_PII_KEYWORDS = ("паспорт", "passport", "снилс", "ИНН", "inn")


def _detect_pii(text_in: str) -> tuple[bool, str]:
    """Вернуть (has_pii, level: 'low'|'high')."""
    if not text_in:
        return False, "low"
    for pat in _BLACKLIST_PATTERNS:
        if pat.search(text_in):
            return True, "high"
    lower = text_in.lower()
    for kw in _PII_KEYWORDS:
        if kw.lower() in lower:
            return True, "high"
    return False, "low"


def _insert_score(workspace_id: str, analysis_job_id: str) -> None:
    with sync_session() as sess:
        sess.execute(
            text(
                "INSERT INTO ai_conversation_scores("
                "  analysis_job_id, workspace_id, overall_score, dimension_scores, "
                "  strengths, weaknesses, recommendations, confidence) "
                "VALUES (CAST(:jid AS UUID), CAST(:wid AS UUID), :overall, "
                "        CAST(:dim AS JSONB), CAST(:str AS JSONB), CAST(:wk AS JSONB), "
                "        CAST(:rec AS JSONB), :conf)"
            ),
            {
                "jid": analysis_job_id,
                "wid": workspace_id,
                "overall": 72.5,
                "dim": '{"greeting": 80, "needs_discovery": 60, "objection_handling": 70, "closing": 75}',
                "str": '["Хорошее приветствие", "Активное слушание"]',
                "wk": '["Слабая проработка возражений", "Нет следующего шага"]',
                "rec": '["Использовать SPIN-методику", "Завершать звонок чёткой договорённостью"]',
                "conf": 0.85,
            },
        )


def _insert_pattern(workspace_id: str, pattern_type: str, freq: str, sample: int, descr: str) -> None:
    with sync_session() as sess:
        sess.execute(
            text(
                "INSERT INTO ai_behavior_patterns("
                "  workspace_id, pattern_type, frequency_bucket, sample_size, "
                "  description, evidence_refs) "
                "VALUES (CAST(:wid AS UUID), :pt, :fb, :ss, :d, CAST('[]' AS JSONB))"
            ),
            {
                "wid": workspace_id,
                "pt": pattern_type,
                "fb": freq,
                "ss": sample,
                "d": descr,
            },
        )


def _insert_kb_item(workspace_id: str, title: str, body: str) -> None:
    with sync_session() as sess:
        sess.execute(
            text(
                "INSERT INTO ai_client_knowledge_items("
                "  workspace_id, source, title, body) "
                "VALUES (CAST(:wid AS UUID), 'extracted_from_cases', :t, :b)"
            ),
            {"wid": workspace_id, "t": title, "b": body},
        )


def _create_analysis_job(
    workspace_id: str,
    connection_id: str | None,
    kind: str,
) -> str:
    """Создать ai_analysis_jobs row и вернуть его id."""
    with sync_session() as sess:
        row = sess.execute(
            text(
                "INSERT INTO ai_analysis_jobs("
                "  workspace_id, crm_connection_id, kind, input_ref, status, started_at) "
                "VALUES (CAST(:wid AS UUID), CAST(:cid AS UUID), :k, "
                "        CAST(:ir AS JSONB), 'running', NOW()) "
                "RETURNING id"
            ),
            {
                "wid": workspace_id,
                "cid": connection_id,
                "k": kind,
                "ir": '{}',
            },
        ).fetchone()
    return str(row[0])


def _finalize_analysis_job(analysis_job_id: str, *, ok: bool, error: str | None = None) -> None:
    with sync_session() as sess:
        if ok:
            sess.execute(
                text(
                    "UPDATE ai_analysis_jobs SET status='succeeded', finished_at=NOW() "
                    "WHERE id = CAST(:jid AS UUID)"
                ),
                {"jid": analysis_job_id},
            )
        else:
            sess.execute(
                text(
                    "UPDATE ai_analysis_jobs SET status='failed', finished_at=NOW(), error=:e "
                    "WHERE id = CAST(:jid AS UUID)"
                ),
                {"jid": analysis_job_id, "e": (error or "unknown")[:1000]},
            )


def analyze_conversation(
    workspace_id: str,
    *,
    connection_id: str | None = None,
    kind: str = "call_transcript",
    job_row_id: str | None = None,
) -> dict[str, Any]:
    """Универсальный анализатор по `kind` (call_transcript / chat_dialog / deal_review)."""
    mark_job_running(job_row_id)
    analysis_job_id: str | None = None
    try:
        analysis_job_id = _create_analysis_job(workspace_id, connection_id, kind)

        # 3 mock insights: 1 score + 1 pattern + 1 kb.
        _insert_score(workspace_id, analysis_job_id)
        _insert_pattern(
            workspace_id,
            "missed_need",
            "medium",
            sample=15,
            descr="Менеджер не уточняет ключевую потребность клиента в первой трети разговора.",
        )
        _insert_kb_item(
            workspace_id,
            title="Чек-лист квалификации лида",
            body="1. Бюджет\n2. Сроки\n3. Лицо принимающее решение",
        )

        _finalize_analysis_job(analysis_job_id, ok=True)
        result = {
            "workspace_id": workspace_id,
            "analysis_job_id": analysis_job_id,
            "kind": kind,
            "insights": 3,
        }
        mark_job_succeeded(job_row_id, result)
        return result
    except Exception as exc:
        if analysis_job_id:
            _finalize_analysis_job(analysis_job_id, ok=False, error=str(exc))
        mark_job_failed(job_row_id, f"analyze_conversation: {exc}")
        raise


def analyze_deals(workspace_id: str, *, connection_id: str | None = None,
                  job_row_id: str | None = None) -> dict[str, Any]:
    return analyze_conversation(
        workspace_id=workspace_id,
        connection_id=connection_id,
        kind="deal_review",
        job_row_id=job_row_id,
    )


def analyze_calls(workspace_id: str, *, connection_id: str | None = None,
                  job_row_id: str | None = None) -> dict[str, Any]:
    return analyze_conversation(
        workspace_id=workspace_id,
        connection_id=connection_id,
        kind="call_transcript",
        job_row_id=job_row_id,
    )


def analyze_chats(workspace_id: str, *, connection_id: str | None = None,
                  job_row_id: str | None = None) -> dict[str, Any]:
    return analyze_conversation(
        workspace_id=workspace_id,
        connection_id=connection_id,
        kind="chat_dialog",
        job_row_id=job_row_id,
    )


def extract_patterns(
    workspace_id: str,
    *,
    job_row_id: str | None = None,
) -> dict[str, Any]:
    """Сгенерировать набор поведенческих паттернов в ai_behavior_patterns."""
    mark_job_running(job_row_id)
    try:
        for ptype, freq, sample, descr in (
            (
                "objection_unhandled",
                "high",
                42,
                "Возражение «дорого» не отрабатывается в 60%+ разговоров.",
            ),
            (
                "no_next_step",
                "medium",
                28,
                "Менеджер не фиксирует следующий шаг в конце разговора.",
            ),
            (
                "long_silence",
                "low",
                12,
                "Паузы > 8 секунд встречаются в начале звонков.",
            ),
        ):
            _insert_pattern(workspace_id, ptype, freq, sample, descr)

        result = {"workspace_id": workspace_id, "patterns_created": 3}
        mark_job_succeeded(job_row_id, result)
        return result
    except Exception as exc:
        mark_job_failed(job_row_id, f"extract_patterns: {exc}")
        raise


def anonymize_patterns(
    text_in: str,
    *,
    industry: str | None = None,
    job_row_id: str | None = None,
) -> dict[str, Any]:
    """
    Проверить текст на PII по блэклисту и решить, можно ли сохранять.

    Возвращает: {has_pii, privacy_risk, should_store, redacted}.
    Если risk='high' → ``should_store=False``: паттерн отбрасывается до агрегации.
    """
    mark_job_running(job_row_id)
    try:
        has_pii, risk = _detect_pii(text_in)
        # Простая редакция: заменяем все блэклист-совпадения на ***.
        redacted = text_in
        for pat in _BLACKLIST_PATTERNS:
            redacted = pat.sub("***", redacted)

        result = {
            "has_pii": has_pii,
            "privacy_risk": risk,
            "should_store": risk == "low",
            "redacted": redacted,
            "industry": industry,
        }
        mark_job_succeeded(job_row_id, result)
        return result
    except Exception as exc:
        mark_job_failed(job_row_id, f"anonymize_patterns: {exc}")
        raise


def update_research_dataset(
    *,
    industry: str | None = None,
    pattern_type: str = "objection_unhandled",
    sample_size: int = 50,
    summary: str = "Возражение «дорого» — типовой паттерн B2C.",
    job_row_id: str | None = None,
) -> dict[str, Any]:
    """Добавить агрегированный анонимный паттерн в ai_research_patterns."""
    mark_job_running(job_row_id)
    try:
        if sample_size < 10:
            raise ValueError("sample_size должен быть >= 10 (анонимность)")
        with sync_session() as sess:
            sess.execute(
                text(
                    "INSERT INTO ai_research_patterns("
                    "  industry, pattern_type, sample_size, confidence, summary) "
                    "VALUES (:ind, :pt, :ss, :conf, :sm)"
                ),
                {
                    "ind": industry,
                    "pt": pattern_type,
                    "ss": sample_size,
                    "conf": 0.78,
                    "sm": summary,
                },
            )
        result = {
            "industry": industry,
            "pattern_type": pattern_type,
            "sample_size": sample_size,
        }
        mark_job_succeeded(job_row_id, result)
        return result
    except Exception as exc:
        mark_job_failed(job_row_id, f"update_research_dataset: {exc}")
        raise
