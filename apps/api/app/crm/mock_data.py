"""
Mock-данные для audit и dashboards в режиме ``MOCK_CRM_MODE=true``.

Если tenant-схема ещё не заполнена реальными данными, эти заглушки
отдают синтетические метрики, чтобы FE мог отрисовать UI.

Правила:
- Детерминированные значения (чтобы тесты были стабильны).
- Маркер ``"mock": True`` во всех объектах.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


def mock_audit_summary(connection_id: str) -> dict[str, Any]:
    """Мок-саммари audit-отчёта по подключению."""
    return {
        "mock": True,
        "connection_id": connection_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "totals": {
            "deals": 12450,
            "contacts": 8300,
            "companies": 1750,
            "calls": 23400,
            "tasks": 9800,
            "notes": 14500,
            "pipelines": 3,
            "stages": 12,
            "users": 24,
        },
        "quality": {
            "score": 78,
            "deals_without_responsible_pct": 4.2,
            "contacts_without_phone_pct": 11.7,
            "deals_without_activity_7d_pct": 23.5,
        },
        "period": {
            "first_event_at": (
                datetime.now(timezone.utc) - timedelta(days=720)
            ).isoformat(),
            "last_event_at": datetime.now(timezone.utc).isoformat(),
        },
        "recommendations": [
            "Заполнить ответственного в 525 сделках без owner'а.",
            "Дособрать phone/email у 971 контакта.",
            "Закрыть или реактивировать 2925 зависших сделок.",
        ],
    }


def mock_dashboard_overview(connection_id: str) -> dict[str, Any]:
    """Overview-метрики: revenue, win-rate, avg cycle, активные сделки."""
    return {
        "mock": True,
        "connection_id": connection_id,
        "period": "last_90_days",
        "total_deals": 100,
        "open_deals": 58,
        "won_deals": 32,
        "lost_deals": 10,
        "revenue_cents": 1_250_000_00,  # 12.5М ₽
        "currency": "RUB",
        "win_rate": 0.32,
        "avg_cycle_days": 11,
        "abandoned_deals": 14,
        "new_deals_last_7d": 22,
        "conversion_from_previous": [
            {"stage": "Первый контакт", "pct": 0.78},
            {"stage": "Квалификация", "pct": 0.61},
            {"stage": "Переговоры", "pct": 0.44},
            {"stage": "КП", "pct": 0.52},
            {"stage": "Оплата", "pct": 0.81},
        ],
    }


def mock_dashboard_funnel(connection_id: str) -> dict[str, Any]:
    """Воронка: stage → count → conversion."""
    stages = [
        {"stage": "Первый контакт", "count": 180, "conversion_from_previous": None},
        {"stage": "Квалификация", "count": 140, "conversion_from_previous": 0.78},
        {"stage": "Переговоры", "count": 86, "conversion_from_previous": 0.61},
        {"stage": "КП отправлено", "count": 38, "conversion_from_previous": 0.44},
        {"stage": "Оплата", "count": 20, "conversion_from_previous": 0.52},
        {"stage": "Выигран", "count": 16, "conversion_from_previous": 0.80},
    ]
    return {
        "mock": True,
        "connection_id": connection_id,
        "stages": stages,
    }


def mock_dashboard_sources(connection_id: str) -> dict[str, Any]:
    """Распределение сделок по источникам."""
    return {
        "mock": True,
        "connection_id": connection_id,
        "sources": [
            {"name": "Сайт", "count": 62, "won": 24, "revenue_cents": 480_00},
            {"name": "Реклама", "count": 48, "won": 14, "revenue_cents": 260_00},
            {"name": "Реферал", "count": 22, "won": 12, "revenue_cents": 310_00},
            {"name": "Холодный обзвон", "count": 18, "won": 2, "revenue_cents": 60_00},
            {"name": "Чат", "count": 30, "won": 10, "revenue_cents": 190_00},
        ],
    }


def mock_dashboard_managers(connection_id: str) -> dict[str, Any]:
    """Менеджеры и их активность."""
    managers = [
        {
            "user_id": "u-1",
            "full_name": "Иванов Иван",
            "deals_open": 18,
            "deals_won": 7,
            "tasks_overdue": 2,
            "calls_last_7d": 38,
        },
        {
            "user_id": "u-2",
            "full_name": "Петров Пётр",
            "deals_open": 14,
            "deals_won": 9,
            "tasks_overdue": 0,
            "calls_last_7d": 42,
        },
        {
            "user_id": "u-3",
            "full_name": "Сидорова Анна",
            "deals_open": 22,
            "deals_won": 12,
            "tasks_overdue": 4,
            "calls_last_7d": 57,
        },
    ]
    return {
        "mock": True,
        "connection_id": connection_id,
        "managers": managers,
    }


def mock_dashboard_calls(connection_id: str) -> dict[str, Any]:
    """Сводка по звонкам."""
    return {
        "mock": True,
        "connection_id": connection_id,
        "total": 1480,
        "inbound": 612,
        "outbound": 868,
        "avg_duration_sec": 186,
        "missed_pct": 0.14,
        "by_day": [
            {"date": "2026-04-11", "total": 52, "missed": 7},
            {"date": "2026-04-12", "total": 61, "missed": 9},
            {"date": "2026-04-13", "total": 44, "missed": 5},
            {"date": "2026-04-14", "total": 72, "missed": 11},
            {"date": "2026-04-15", "total": 68, "missed": 8},
            {"date": "2026-04-16", "total": 55, "missed": 6},
            {"date": "2026-04-17", "total": 49, "missed": 4},
        ],
    }


def mock_dashboard_messages(connection_id: str) -> dict[str, Any]:
    """Сводка по сообщениям (чаты, email)."""
    return {
        "mock": True,
        "connection_id": connection_id,
        "total": 4120,
        "by_channel": [
            {"channel": "whatsapp", "count": 1850, "avg_response_min": 12},
            {"channel": "telegram", "count": 1240, "avg_response_min": 8},
            {"channel": "site", "count": 620, "avg_response_min": 22},
            {"channel": "email", "count": 410, "avg_response_min": 96},
        ],
    }


def mock_conversation_scores(connection_id: str) -> list[dict[str, Any]]:
    """Список последних AI-оценок разговоров."""
    return [
        {
            "id": "score-1",
            "connection_id": connection_id,
            "overall_score": 78.5,
            "dimension_scores": {
                "greeting": 85,
                "needs_discovery": 62,
                "objection_handling": 80,
                "closing": 88,
            },
            "confidence": 0.82,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "mock": True,
        },
        {
            "id": "score-2",
            "connection_id": connection_id,
            "overall_score": 64.0,
            "dimension_scores": {
                "greeting": 72,
                "needs_discovery": 48,
                "objection_handling": 60,
                "closing": 76,
            },
            "confidence": 0.71,
            "created_at": (
                datetime.now(timezone.utc) - timedelta(hours=3)
            ).isoformat(),
            "mock": True,
        },
    ]


def mock_behavior_patterns(connection_id: str) -> list[dict[str, Any]]:
    """Типовые поведенческие паттерны менеджеров."""
    return [
        {
            "id": "bp-1",
            "connection_id": connection_id,
            "pattern_type": "missed_need",
            "frequency_bucket": "high",
            "sample_size": 126,
            "description": "Менеджеры не уточняют бюджет в ≥40% звонков.",
            "mock": True,
        },
        {
            "id": "bp-2",
            "connection_id": connection_id,
            "pattern_type": "no_next_step",
            "frequency_bucket": "medium",
            "sample_size": 88,
            "description": "После звонка не создаётся follow-up задача.",
            "mock": True,
        },
        {
            "id": "bp-3",
            "connection_id": connection_id,
            "pattern_type": "long_silence",
            "frequency_bucket": "low",
            "sample_size": 42,
            "description": "Паузы >12 сек в переговорах с клиентом.",
            "mock": True,
        },
    ]
