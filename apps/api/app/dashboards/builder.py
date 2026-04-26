"""Dashboard builder API and public read-only dashboard shares."""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.db import get_session
from app.core.settings import get_settings
from app.dashboards.router import (
    _dashboard_filter_state,
    _dashboard_filters,
    _iso,
    _mock_sales_dashboard,
    _resolve_conn,
    _rub,
    _set_search_path,
    _use_mock,
    _where_with_extra,
)
from app.db.models import (
    CrmConnection,
    Dashboard,
    DashboardShare,
    DashboardWidget,
    User,
)

router = APIRouter(tags=["dashboard-builder"])
settings = get_settings()

DEFAULT_PAGES: list[dict[str, str]] = [
    {"page_key": "sales", "title": "Продажи"},
    {"page_key": "pipelines", "title": "Воронки"},
    {"page_key": "managers", "title": "Менеджеры"},
    {"page_key": "risks", "title": "Риски"},
]
LEGACY_PAGE: dict[str, str] = {"page_key": "main", "title": "Основная"}

CATALOG_ITEMS: list[dict[str, Any]] = [
    {"widget_type": "kpi_applications", "title": "Заявки", "group": "kpi", "w": 3, "h": 3},
    {"widget_type": "kpi_open", "title": "Открытые", "group": "kpi", "w": 3, "h": 3},
    {"widget_type": "kpi_sales_count", "title": "Продаж", "group": "kpi", "w": 3, "h": 3},
    {"widget_type": "kpi_lost", "title": "Не реализовано", "group": "kpi", "w": 3, "h": 3},
    {"widget_type": "kpi_sales_amount", "title": "Продажи руб", "group": "kpi", "w": 3, "h": 3},
    {"widget_type": "kpi_avg_deal", "title": "Средний чек", "group": "kpi", "w": 3, "h": 3},
    {"widget_type": "kpi_conversion", "title": "Конверсия", "group": "kpi", "w": 3, "h": 3},
    {"widget_type": "kpi_pipeline_count", "title": "Воронки", "group": "kpi", "w": 3, "h": 3},
    {"widget_type": "kpi_manager_count", "title": "Менеджеры", "group": "kpi", "w": 3, "h": 3},
    {"widget_type": "line_dynamics", "title": "Заявки / продажи / проиграно", "group": "dynamics", "w": 8, "h": 5},
    {"widget_type": "revenue_dynamics", "title": "Выручка и продажи", "group": "dynamics", "w": 8, "h": 5},
    {"widget_type": "status_structure", "title": "Структура статусов", "group": "dynamics", "w": 5, "h": 5},
    {"widget_type": "stage_funnel", "title": "Воронка по этапам", "group": "pipelines", "w": 6, "h": 5},
    {"widget_type": "pipeline_table", "title": "Таблица воронок", "group": "pipelines", "w": 6, "h": 5},
    {"widget_type": "pipeline_health", "title": "Здоровье воронок", "group": "pipelines", "w": 7, "h": 5},
    {"widget_type": "pipeline_stale", "title": "Зависшие по воронкам", "group": "pipelines", "w": 6, "h": 5},
    {"widget_type": "manager_table", "title": "Таблица менеджеров", "group": "managers", "w": 8, "h": 6},
    {"widget_type": "manager_revenue_rank", "title": "Менеджеры по выручке", "group": "managers", "w": 6, "h": 5},
    {"widget_type": "manager_conversion_rank", "title": "Менеджеры по конверсии", "group": "managers", "w": 6, "h": 5},
    {"widget_type": "manager_risk", "title": "Риски по менеджерам", "group": "managers", "w": 7, "h": 5},
    {"widget_type": "top_deals", "title": "Топ сделок", "group": "risks", "w": 6, "h": 5},
    {"widget_type": "open_age_buckets", "title": "Возраст открытых сделок", "group": "risks", "w": 7, "h": 5},
    {"widget_type": "phase2b_calls", "title": "Звонки", "group": "phase2b", "w": 4, "h": 3, "placeholder": True},
    {"widget_type": "phase2b_messages", "title": "Сообщения", "group": "phase2b", "w": 4, "h": 3, "placeholder": True},
    {"widget_type": "phase2b_email", "title": "Почта", "group": "phase2b", "w": 4, "h": 3, "placeholder": True},
    {"widget_type": "phase2b_sources", "title": "Источники", "group": "phase2b", "w": 4, "h": 3, "placeholder": True},
    {"widget_type": "phase2b_lost_reasons", "title": "Причины отказов", "group": "phase2b", "w": 5, "h": 4, "placeholder": True},
]


def _extended_widget(
    widget_type: str,
    title: str,
    group: str,
    *,
    w: int = 4,
    h: int = 3,
    availability: str = "available",
    requirements: list[str] | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    return {
        "widget_type": widget_type,
        "title": title,
        "group": group,
        "w": w,
        "h": h,
        "availability": availability,
        "requirements": requirements or [],
        "description": description,
        "placeholder": availability != "available",
    }


UNIVERSAL_ANALYTICS_ITEMS: list[dict[str, Any]] = [
    # KPI and sales
    _extended_widget("kpi_plan_revenue", "План выручки", "kpi", availability="requires_mapping", requirements=["revenue_plan"], description="Плановая выручка из выбранного поля amoCRM."),
    _extended_widget("kpi_revenue_plan_fact", "План/факт выручки", "kpi", availability="requires_mapping", requirements=["revenue_plan"]),
    _extended_widget("kpi_plan_completion", "Выполнение плана", "kpi", availability="requires_mapping", requirements=["revenue_plan"]),
    _extended_widget("kpi_sales_cycle", "Цикл сделки", "kpi", availability="available"),
    _extended_widget("kpi_repeat_sales", "Повторные продажи", "kpi", availability="requires_mapping", requirements=["customer_key"]),
    _extended_widget("kpi_margin", "Маржа", "kpi", availability="requires_mapping", requirements=["margin"]),
    _extended_widget("sales_won_lost_dynamics", "Выиграно / проиграно", "sales", w=8, h=5),
    _extended_widget("sales_payment_dynamics", "Динамика оплат", "sales", w=8, h=5, availability="requires_mapping", requirements=["paid_amount"]),
    _extended_widget("sales_top_products", "Топ товаров / услуг", "sales", w=6, h=5, availability="requires_mapping", requirements=["product"]),
    _extended_widget("sales_lost_by_stage", "Потери по этапам", "sales", w=7, h=5),
    _extended_widget("sales_stage_velocity", "Скорость этапов", "sales", w=7, h=5),
    _extended_widget("sales_deals_table", "Таблица сделок", "sales", w=10, h=6),
    _extended_widget("sales_forecast", "Прогноз продаж", "sales", w=6, h=5, availability="requires_ai", requirements=["ai_forecast"]),
    _extended_widget("sales_no_next_step", "Сделки без следующего шага", "sales", w=6, h=5, availability="requires_integration", requirements=["tasks"]),
    # Revenue and finance
    _extended_widget("revenue_plan_vs_fact_line", "План/факт по месяцам", "finance", w=8, h=5, availability="requires_mapping", requirements=["revenue_plan"]),
    _extended_widget("revenue_avg_check_dynamics", "Динамика среднего чека", "finance", w=8, h=5),
    _extended_widget("revenue_by_manager", "Выручка по менеджерам", "finance", w=6, h=5),
    _extended_widget("revenue_by_pipeline", "Выручка по воронкам", "finance", w=6, h=5),
    _extended_widget("revenue_by_stage", "Выручка по этапам", "finance", w=6, h=5),
    _extended_widget("finance_paid_amount", "Оплачено", "finance", w=4, h=3, availability="requires_mapping", requirements=["paid_amount"]),
    _extended_widget("finance_debt_amount", "Должны оплатить", "finance", w=4, h=3, availability="requires_mapping", requirements=["debt_amount"]),
    _extended_widget("finance_unsigned_acts", "Не подписаны акты", "finance", w=4, h=3, availability="requires_mapping", requirements=["act_signed_amount"]),
    _extended_widget("finance_margin_by_manager", "Маржа по менеджерам", "finance", w=6, h=5, availability="requires_mapping", requirements=["margin"]),
    _extended_widget("finance_margin_dynamics", "Динамика маржи", "finance", w=8, h=5, availability="requires_mapping", requirements=["margin"]),
    # Pipelines
    _extended_widget("pipeline_conversion_by_stage", "Конверсия этапов", "pipelines", w=7, h=5),
    _extended_widget("pipeline_dropoff_by_stage", "Отвал по этапам", "pipelines", w=7, h=5),
    _extended_widget("pipeline_stage_age", "Возраст сделок по этапам", "pipelines", w=7, h=5),
    _extended_widget("pipeline_stage_amount", "Сумма по этапам", "pipelines", w=7, h=5),
    _extended_widget("pipeline_manager_mix", "Менеджеры по воронкам", "pipelines", w=7, h=5),
    _extended_widget("pipeline_heatmap", "Тепловая карта воронок", "pipelines", w=8, h=5),
    _extended_widget("pipeline_no_activity", "Сделки без активности", "pipelines", w=6, h=5, availability="requires_integration", requirements=["notes", "tasks"]),
    # Managers
    _extended_widget("manager_sales_cycle", "Цикл сделки по менеджерам", "managers", w=7, h=5),
    _extended_widget("manager_avg_check_rank", "Средний чек менеджеров", "managers", w=6, h=5),
    _extended_widget("manager_plan_completion", "План менеджеров", "managers", w=7, h=5, availability="requires_mapping", requirements=["revenue_plan"]),
    _extended_widget("manager_overdue_tasks", "Просрочки менеджеров", "managers", w=7, h=5, availability="requires_integration", requirements=["tasks"]),
    _extended_widget("manager_activity_score", "Активность менеджеров", "managers", w=7, h=5, availability="requires_integration", requirements=["tasks", "notes", "calls", "messages"]),
    _extended_widget("manager_communications_table", "Коммуникации менеджеров", "managers", w=9, h=6, availability="requires_integration", requirements=["calls", "messages", "email"]),
    _extended_widget("manager_quality_score", "Качество менеджеров", "managers", w=7, h=5, availability="requires_ai", requirements=["ai_quality"]),
    _extended_widget("manager_coaching_plan", "План обучения", "managers", w=7, h=5, availability="requires_ai", requirements=["ai_coaching"]),
    # Counterparties
    _extended_widget("counterparty_count", "Контрагентов", "counterparties"),
    _extended_widget("counterparty_top_paid", "Топ оплативших клиентов", "counterparties", w=7, h=5, availability="requires_mapping", requirements=["paid_amount"]),
    _extended_widget("counterparty_top_debt", "Топ должников", "counterparties", w=7, h=5, availability="requires_mapping", requirements=["debt_amount"]),
    _extended_widget("counterparty_unsigned_acts", "Акты по контрагентам", "counterparties", w=7, h=5, availability="requires_mapping", requirements=["act_signed_amount"]),
    _extended_widget("counterparty_repeat_rate", "Повторные клиенты", "counterparties", w=5, h=4),
    _extended_widget("counterparty_ltv", "LTV клиента", "counterparties", w=6, h=5, availability="requires_mapping", requirements=["customer_key"]),
    _extended_widget("counterparty_first_last_payment", "Первый / последний платёж", "counterparties", w=8, h=5, availability="requires_mapping", requirements=["paid_amount"]),
    _extended_widget("counterparty_inactive", "Давно не покупали", "counterparties", w=7, h=5),
    _extended_widget("counterparty_table", "Таблица контрагентов", "counterparties", w=10, h=6),
    # Marketing
    _extended_widget("marketing_source_leads", "Лиды по источникам", "marketing", w=6, h=5, availability="requires_mapping", requirements=["source"]),
    _extended_widget("marketing_source_sales", "Продажи по источникам", "marketing", w=6, h=5, availability="requires_mapping", requirements=["source"]),
    _extended_widget("marketing_source_revenue", "Выручка по источникам", "marketing", w=6, h=5, availability="requires_mapping", requirements=["source"]),
    _extended_widget("marketing_source_conversion", "Конверсия источников", "marketing", w=6, h=5, availability="requires_mapping", requirements=["source"]),
    _extended_widget("marketing_utm_campaigns", "UTM-кампании", "marketing", w=8, h=5, availability="requires_mapping", requirements=["utm_campaign"]),
    _extended_widget("marketing_channel_roi", "ROI каналов", "marketing", w=7, h=5, availability="requires_mapping", requirements=["ad_cost", "source"]),
    _extended_widget("marketing_lead_quality", "Качество лидов", "marketing", w=7, h=5, availability="requires_ai", requirements=["ai_lead_quality"]),
    # Tasks and processes
    _extended_widget("tasks_overdue", "Просроченные задачи", "tasks", w=5, h=4, availability="requires_integration", requirements=["tasks"]),
    _extended_widget("tasks_by_manager", "Задачи по менеджерам", "tasks", w=7, h=5, availability="requires_integration", requirements=["tasks"]),
    _extended_widget("tasks_completion_rate", "Выполнение задач", "tasks", w=6, h=5, availability="requires_integration", requirements=["tasks"]),
    _extended_widget("tasks_no_answer", "Задачи без ответа", "tasks", w=6, h=5, availability="requires_integration", requirements=["tasks", "notes"]),
    _extended_widget("tasks_sla_reaction", "SLA реакции", "tasks", w=7, h=5, availability="requires_integration", requirements=["tasks", "notes"]),
    _extended_widget("tasks_next_action_missing", "Нет следующего шага", "tasks", w=6, h=5, availability="requires_integration", requirements=["tasks"]),
    # Calls
    _extended_widget("calls_count", "Количество звонков", "calls", availability="requires_integration", requirements=["calls"]),
    _extended_widget("calls_in_out_dynamics", "Входящие / исходящие", "calls", w=8, h=5, availability="requires_integration", requirements=["calls"]),
    _extended_widget("calls_duration_total", "Длительность звонков", "calls", availability="requires_integration", requirements=["calls"]),
    _extended_widget("calls_avg_duration", "Средняя длительность", "calls", availability="requires_integration", requirements=["calls"]),
    _extended_widget("calls_result_pie", "Результаты звонков", "calls", w=6, h=5, availability="requires_integration", requirements=["calls"]),
    _extended_widget("calls_duration_by_manager", "Длительность по менеджерам", "calls", w=7, h=5, availability="requires_integration", requirements=["calls"]),
    _extended_widget("calls_count_by_stage", "Звонки по этапам", "calls", w=7, h=5, availability="requires_integration", requirements=["calls"]),
    _extended_widget("calls_missed", "Пропущенные звонки", "calls", w=6, h=5, availability="requires_integration", requirements=["calls"]),
    # Messages and email
    _extended_widget("messages_dialog_count", "Диалоги", "communications", availability="requires_integration", requirements=["messages"]),
    _extended_widget("messages_response_sla", "Скорость ответа", "communications", w=7, h=5, availability="requires_integration", requirements=["messages"]),
    _extended_widget("messages_unanswered", "Неотвеченные сообщения", "communications", w=6, h=5, availability="requires_integration", requirements=["messages"]),
    _extended_widget("messages_by_manager", "Сообщения по менеджерам", "communications", w=7, h=5, availability="requires_integration", requirements=["messages"]),
    _extended_widget("email_sent_count", "Отправлено писем", "communications", availability="requires_integration", requirements=["email"]),
    _extended_widget("email_response_sla", "Скорость ответа на почту", "communications", w=7, h=5, availability="requires_integration", requirements=["email"]),
    _extended_widget("communications_per_deal", "Коммуникаций на сделку", "communications", w=7, h=5, availability="requires_integration", requirements=["calls", "messages", "email"]),
    _extended_widget("communications_timeline", "Таймлайн коммуникаций", "communications", w=10, h=6, availability="requires_integration", requirements=["calls", "messages", "email"]),
    # AI
    _extended_widget("ai_script_adherence", "Соблюдение скрипта", "ai", w=7, h=5, availability="requires_ai", requirements=["ai_calls"]),
    _extended_widget("ai_keywords", "Ключевые слова", "ai", w=7, h=5, availability="requires_ai", requirements=["ai_text"]),
    _extended_widget("ai_objection_reasons", "Возражения и причины отказов", "ai", w=7, h=5, availability="requires_ai", requirements=["ai_text"]),
    _extended_widget("ai_client_sentiment", "Настроение клиента", "ai", w=6, h=5, availability="requires_ai", requirements=["ai_sentiment"]),
    _extended_widget("ai_manager_score", "AI-оценка менеджера", "ai", w=6, h=5, availability="requires_ai", requirements=["ai_quality"]),
    _extended_widget("ai_deal_recommendations", "Рекомендации по сделке", "ai", w=7, h=5, availability="requires_ai", requirements=["ai_deals"]),
    _extended_widget("ai_risk_deals", "Рискованные сделки", "ai", w=7, h=5, availability="requires_ai", requirements=["ai_risk"]),
    _extended_widget("ai_training_topics", "Темы для обучения", "ai", w=7, h=5, availability="requires_ai", requirements=["ai_coaching"]),
    _extended_widget("ai_best_practices", "Лучшие практики продаж", "ai", w=7, h=5, availability="requires_ai", requirements=["ai_quality"]),
    _extended_widget("ai_token_estimate", "Оценка токенов AI", "ai", w=5, h=4, availability="requires_ai", requirements=["ai_token_estimate"]),
]

CATALOG_ITEMS.extend(UNIVERSAL_ANALYTICS_ITEMS)
UNIVERSAL_ANALYTICS_WIDGET_COUNT = len(CATALOG_ITEMS)

DASHBOARD_TEMPLATES: list[dict[str, Any]] = [
    {"template_key": "sales_leads", "title": "Продажи и лиды", "category": "sales", "widgets": ["kpi_applications", "kpi_sales_count", "kpi_sales_amount", "kpi_conversion", "line_dynamics", "sales_won_lost_dynamics"]},
    {"template_key": "revenue_avg_check", "title": "Выручка и средний чек", "category": "finance", "widgets": ["kpi_plan_revenue", "kpi_revenue_plan_fact", "kpi_avg_deal", "revenue_avg_check_dynamics", "revenue_plan_vs_fact_line", "finance_margin_dynamics"]},
    {"template_key": "pipelines_stages", "title": "Воронки и этапы", "category": "pipelines", "widgets": ["stage_funnel", "pipeline_conversion_by_stage", "pipeline_dropoff_by_stage", "pipeline_stage_age", "pipeline_health"]},
    {"template_key": "manager_rop", "title": "Менеджеры / РОП", "category": "managers", "widgets": ["manager_table", "manager_revenue_rank", "manager_conversion_rank", "manager_sales_cycle", "manager_activity_score", "manager_quality_score"]},
    {"template_key": "counterparties", "title": "Клиенты и контрагенты", "category": "counterparties", "widgets": ["counterparty_count", "counterparty_top_paid", "counterparty_top_debt", "counterparty_unsigned_acts", "counterparty_table"]},
    {"template_key": "marketing_sources", "title": "Маркетинг и источники", "category": "marketing", "widgets": ["marketing_source_leads", "marketing_source_sales", "marketing_source_revenue", "marketing_source_conversion", "marketing_utm_campaigns"]},
    {"template_key": "tasks_processes", "title": "Задачи и процессы", "category": "tasks", "widgets": ["tasks_overdue", "tasks_by_manager", "tasks_completion_rate", "tasks_sla_reaction", "tasks_next_action_missing"]},
    {"template_key": "calls", "title": "Звонки", "category": "calls", "widgets": ["calls_count", "calls_in_out_dynamics", "calls_duration_total", "calls_result_pie", "calls_duration_by_manager"]},
    {"template_key": "messages_email", "title": "Сообщения и почта", "category": "communications", "widgets": ["messages_dialog_count", "messages_response_sla", "messages_unanswered", "email_sent_count", "communications_timeline"]},
    {"template_key": "ai_quality", "title": "AI-контроль качества", "category": "ai", "widgets": ["ai_script_adherence", "ai_keywords", "ai_objection_reasons", "ai_client_sentiment", "ai_manager_score"]},
    {"template_key": "owner_risks", "title": "Риски владельца", "category": "risks", "widgets": ["open_age_buckets", "pipeline_stale", "manager_risk", "finance_debt_amount", "ai_risk_deals"]},
]
WIDGET_CATALOG: dict[str, dict[str, Any]] = {
    str(item["widget_type"]): item for item in CATALOG_ITEMS
}

DEFAULT_WIDGETS: list[dict[str, Any]] = [
    {"widget_type": "kpi_applications", "title": "Заявки", "x": 0, "y": 0, "w": 3, "h": 3, "config": {"page_key": "sales"}},
    {"widget_type": "kpi_lost", "title": "Не реализовано", "x": 3, "y": 0, "w": 3, "h": 3, "config": {"page_key": "sales"}},
    {"widget_type": "kpi_sales_count", "title": "Продаж", "x": 6, "y": 0, "w": 3, "h": 3, "config": {"page_key": "sales"}},
    {"widget_type": "kpi_sales_amount", "title": "Продажи руб", "x": 9, "y": 0, "w": 3, "h": 3, "config": {"page_key": "sales"}},
    {"widget_type": "line_dynamics", "title": "Динамика лидов и оплат", "x": 0, "y": 3, "w": 8, "h": 5, "config": {"page_key": "sales"}},
    {"widget_type": "stage_funnel", "title": "Воронка по этапам", "x": 0, "y": 0, "w": 7, "h": 5, "config": {"page_key": "pipelines"}},
    {"widget_type": "pipeline_health", "title": "Здоровье воронок", "x": 0, "y": 5, "w": 8, "h": 5, "config": {"page_key": "pipelines"}},
    {"widget_type": "manager_table", "title": "Менеджеры", "x": 0, "y": 0, "w": 12, "h": 6, "config": {"page_key": "managers"}},
    {"widget_type": "manager_risk", "title": "Риски по менеджерам", "x": 0, "y": 0, "w": 7, "h": 5, "config": {"page_key": "risks"}},
    {"widget_type": "open_age_buckets", "title": "Возраст открытых сделок", "x": 0, "y": 5, "w": 7, "h": 5, "config": {"page_key": "risks"}},
]


class DashboardWidgetIn(BaseModel):
    widget_key: str | None = None
    widget_type: str
    title: str | None = None
    x: int = 0
    y: int = 0
    w: int = 4
    h: int = 3
    config: dict[str, Any] = Field(default_factory=dict)


class DashboardPageIn(BaseModel):
    page_key: str
    title: str


class DashboardBuilderSaveIn(BaseModel):
    name: str = "Основной дашборд"
    filters: dict[str, Any] = Field(default_factory=dict)
    pages: list[DashboardPageIn] = Field(default_factory=list)
    widgets: list[DashboardWidgetIn]


def hash_share_token(share_token: str) -> str:
    """Hash public share tokens before storage."""
    return hashlib.sha256(share_token.encode("utf-8")).hexdigest()


def _new_share_token() -> str:
    return secrets.token_urlsafe(32)


def _frontend_origin() -> str:
    for origin in settings.allowed_origins_list:
        cleaned = origin.rstrip("/")
        if cleaned.startswith("http") and "api." not in cleaned and "demo." not in cleaned:
            return cleaned
    if settings.base_url.startswith("https://api."):
        return settings.base_url.replace("https://api.", "https://", 1).rstrip("/")
    if settings.base_url.startswith("http://api."):
        return settings.base_url.replace("http://api.", "http://", 1).rstrip("/")
    return settings.base_url.rstrip("/") or "http://localhost:3000"


def _share_url(share_token: str) -> str:
    return f"{_frontend_origin()}/ru/embed/dashboards/{share_token}"


def _clamp_int(value: int, min_value: int, max_value: int) -> int:
    return max(min_value, min(max_value, int(value)))


def _clean_page_key(raw: str, fallback: str) -> str:
    cleaned = "".join(ch for ch in str(raw).strip().lower() if ch.isalnum() or ch in "-_")
    return (cleaned or fallback)[:60]


def _normalize_pages(raw_pages: Any, *, default_to_full: bool = False) -> list[dict[str, str]]:
    source = raw_pages if isinstance(raw_pages, list) and raw_pages else None
    if source is None:
        return [dict(page) for page in (DEFAULT_PAGES if default_to_full else [LEGACY_PAGE])]

    pages: list[dict[str, str]] = []
    seen: set[str] = set()
    for idx, raw in enumerate(source[:12]):
        if isinstance(raw, DashboardPageIn):
            raw_key = raw.page_key
            raw_title = raw.title
        elif isinstance(raw, dict):
            raw_key = raw.get("page_key") or raw.get("key") or f"page-{idx + 1}"
            raw_title = raw.get("title") or raw.get("name") or f"Страница {idx + 1}"
        else:
            continue
        page_key = _clean_page_key(str(raw_key), f"page-{idx + 1}")
        if page_key in seen:
            page_key = _clean_page_key(f"{page_key}-{idx + 1}", f"page-{idx + 1}")
        seen.add(page_key)
        pages.append({"page_key": page_key, "title": str(raw_title).strip()[:80] or f"Страница {idx + 1}"})

    return pages or [dict(page) for page in (DEFAULT_PAGES if default_to_full else [LEGACY_PAGE])]


def _dashboard_pages(dashboard: Dashboard) -> list[dict[str, str]]:
    metadata = dashboard.metadata_json if isinstance(dashboard.metadata_json, dict) else {}
    return _normalize_pages(metadata.get("pages"), default_to_full=False)


def _catalog_payload() -> list[dict[str, Any]]:
    return [
        {
            "widget_type": item["widget_type"],
            "title": item["title"],
            "group": item["group"],
            "w": item["w"],
            "h": item["h"],
            "availability": item.get(
                "availability",
                "requires_integration" if item.get("placeholder") else "available",
            ),
            "requirements": item.get("requirements", []),
            "description": item.get("description"),
            "placeholder": bool(item.get("placeholder")),
        }
        for item in CATALOG_ITEMS
    ]


def _template_payload() -> list[dict[str, Any]]:
    return [
        {
            "template_key": item["template_key"],
            "title": item["title"],
            "category": item["category"],
            "widgets": item["widgets"],
            "requirements": sorted(
                {
                    requirement
                    for widget_type in item["widgets"]
                    for requirement in WIDGET_CATALOG.get(widget_type, {}).get("requirements", [])
                }
            ),
        }
        for item in DASHBOARD_TEMPLATES
    ]


def _clean_widget(
    item: DashboardWidgetIn,
    index: int,
    *,
    page_keys: set[str] | None = None,
    default_page_key: str = "main",
) -> dict[str, Any]:
    if item.widget_type not in WIDGET_CATALOG:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": {
                    "code": "validation_error",
                    "message": f"Unsupported widget type: {item.widget_type}",
                }
            },
        )
    defaults = WIDGET_CATALOG[item.widget_type]
    widget_key = (item.widget_key or f"{item.widget_type}-{index + 1}").strip()
    if not widget_key:
        widget_key = f"{item.widget_type}-{index + 1}"
    config = item.config if isinstance(item.config, dict) else {}
    page_key = _clean_page_key(str(config.get("page_key") or default_page_key), default_page_key)
    if page_keys and page_key not in page_keys:
        page_key = default_page_key
    clean_config = dict(config)
    clean_config["page_key"] = page_key
    return {
        "widget_key": widget_key[:80],
        "widget_type": item.widget_type,
        "title": (item.title or defaults["title"])[:120],
        "x": _clamp_int(item.x, 0, 11),
        "y": _clamp_int(item.y, 0, 999),
        "w": _clamp_int(item.w or defaults["w"], 2, 12),
        "h": _clamp_int(item.h or defaults["h"], 2, 12),
        "config": clean_config,
    }


def _serialize_widget(
    widget: DashboardWidget,
    page_keys: set[str] | None = None,
    default_page_key: str = "main",
) -> dict[str, Any]:
    config = widget.config if isinstance(widget.config, dict) else {}
    page_key = _clean_page_key(str(config.get("page_key") or default_page_key), default_page_key)
    if page_keys and page_key not in page_keys:
        page_key = default_page_key
    clean_config = dict(config)
    clean_config["page_key"] = page_key
    return {
        "id": str(widget.id),
        "widget_key": widget.widget_key,
        "widget_type": widget.widget_type,
        "title": widget.title,
        "x": widget.x,
        "y": widget.y,
        "w": widget.w,
        "h": widget.h,
        "config": clean_config,
    }


def _serialize_dashboard(
    dashboard: Dashboard,
    widgets: list[DashboardWidget],
    active_share: DashboardShare | None,
    *,
    share_url: str | None = None,
) -> dict[str, Any]:
    pages = _dashboard_pages(dashboard)
    page_keys = {page["page_key"] for page in pages}
    default_page_key = pages[0]["page_key"] if pages else "main"
    return {
        "dashboard": {
            "id": str(dashboard.id),
            "name": dashboard.name,
            "filters": dashboard.filters or {},
            "created_at": _iso(dashboard.created_at),
            "updated_at": _iso(dashboard.updated_at),
        },
        "pages": pages,
        "widgets": [_serialize_widget(widget, page_keys, default_page_key) for widget in widgets],
        "share": {
            "enabled": active_share is not None,
            "share_url": share_url,
            "created_at": _iso(active_share.created_at) if active_share else None,
            "last_accessed_at": _iso(active_share.last_accessed_at) if active_share else None,
        },
        "widget_catalog": _catalog_payload(),
        "dashboard_templates": _template_payload(),
    }


async def _ensure_dashboard(
    session: AsyncSession,
    conn: CrmConnection,
    user: User | None,
) -> Dashboard:
    dashboard = (
        await session.execute(
            select(Dashboard)
            .where(Dashboard.crm_connection_id == conn.id)
            .where(Dashboard.status == "active")
            .order_by(Dashboard.created_at.asc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if dashboard:
        return dashboard

    dashboard = Dashboard(
        workspace_id=conn.workspace_id,
        crm_connection_id=conn.id,
        created_by_user_id=user.id if user else None,
        name="Основной дашборд",
        filters={},
        metadata_json={"pages": [dict(page) for page in DEFAULT_PAGES]},
    )
    session.add(dashboard)
    await session.flush()
    page_keys = {page["page_key"] for page in DEFAULT_PAGES}
    for idx, raw in enumerate(DEFAULT_WIDGETS):
        clean = _clean_widget(
            DashboardWidgetIn(**raw),
            idx,
            page_keys=page_keys,
            default_page_key=DEFAULT_PAGES[0]["page_key"],
        )
        session.add(DashboardWidget(dashboard_id=dashboard.id, **clean))
    await session.commit()
    await session.refresh(dashboard)
    return dashboard


async def _dashboard_widgets(session: AsyncSession, dashboard_id: uuid.UUID) -> list[DashboardWidget]:
    return list(
        (
            await session.execute(
                select(DashboardWidget)
                .where(DashboardWidget.dashboard_id == dashboard_id)
                .order_by(DashboardWidget.y.asc(), DashboardWidget.x.asc(), DashboardWidget.created_at.asc())
            )
        )
        .scalars()
        .all()
    )


async def _active_share(session: AsyncSession, dashboard_id: uuid.UUID) -> DashboardShare | None:
    return (
        await session.execute(
            select(DashboardShare)
            .where(DashboardShare.dashboard_id == dashboard_id)
            .where(DashboardShare.status == "active")
            .order_by(DashboardShare.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


def _state_from_dashboard_filters(conn: CrmConnection, filters: dict[str, Any]) -> dict[str, Any]:
    state = _dashboard_filter_state(
        conn,
        period=filters.get("period"),
        date_from=filters.get("date_from"),
        date_to=filters.get("date_to"),
        pipeline_id=filters.get("pipeline_id"),
    )
    pipeline_ids = filters.get("pipeline_ids")
    if isinstance(pipeline_ids, list) and pipeline_ids:
        safe_ids = [str(item) for item in pipeline_ids if str(item).strip()]
        if safe_ids:
            state["pipeline_ids"] = safe_ids
    return state


async def _build_sales_snapshot(
    session: AsyncSession,
    conn: CrmConnection,
    dashboard: Dashboard,
) -> dict[str, Any]:
    if _use_mock(conn):
        return _mock_sales_dashboard(str(conn.id))

    await _set_search_path(session, conn.tenant_schema)
    filters = _state_from_dashboard_filters(conn, dashboard.filters or {})
    where_sql, params = _dashboard_filters(conn, filters=filters)
    monthly_where_sql = (
        f"{where_sql} AND d.created_at_external IS NOT NULL"
        if where_sql
        else "WHERE d.created_at_external IS NOT NULL"
    )

    stats = (
        await session.execute(
            text(
                "SELECT "
                "  COUNT(d.id), "
                "  COUNT(d.id) FILTER (WHERE d.status='open'), "
                "  COUNT(d.id) FILTER (WHERE d.status='won'), "
                "  COUNT(d.id) FILTER (WHERE d.status='lost'), "
                "  COALESCE(SUM(d.price_cents) FILTER (WHERE d.status='won'), 0), "
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
    won_deals = int(stats[2] or 0) if stats else 0
    lost_deals = int(stats[3] or 0) if stats else 0

    monthly_rows = (
        await session.execute(
            text(
                "SELECT date_trunc('month', d.created_at_external)::date AS month, "
                "       COUNT(d.id), "
                "       COUNT(d.id) FILTER (WHERE d.status='won'), "
                "       COUNT(d.id) FILTER (WHERE d.status='lost'), "
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
                "SELECT COALESCE(p.name, 'Без воронки'), COALESCE(s.name, 'Без этапа'), "
                "       COUNT(d.id), "
                "       COALESCE(SUM(d.price_cents) FILTER (WHERE d.status='won'), 0) "
                "FROM deals d "
                "LEFT JOIN pipelines p ON p.id = d.pipeline_id "
                "LEFT JOIN stages s ON s.id = d.stage_id "
                f"{where_sql} "
                "GROUP BY p.id, p.name, s.id, s.name, s.sort_order "
                "ORDER BY COALESCE(s.sort_order, 999999), COUNT(d.id) DESC "
                "LIMIT 80"
            ),
            params,
        )
    ).all()
    manager_where_sql = _where_with_extra(where_sql, "COALESCE(u.is_active, TRUE) IS TRUE")
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
                "LIMIT 40"
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

    manager_metrics = [
        {
            "user_id": str(row[0]),
            "name": row[1],
            "applications": int(row[2] or 0),
            "calls": 0,
            "sales_count": int(row[4] or 0),
            "not_sales_count": int(row[5] or 0),
            "sales_amount": _rub(row[6]),
            "conversion": round(float(row[4] or 0) / float(row[2] or 1), 4),
            "calls_in": 0,
            "calls_out": 0,
            "calls_duration_sec": 0,
            "messages_count": 0,
            "emails_sent": 0,
            "currency": "RUB",
        }
        for row in manager_rows
    ]

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
            "open_deals": int(stats[1] or 0) if stats else 0,
            "won_deals": won_deals,
            "lost_deals": lost_deals,
            "won_rate": round(won_deals / total_deals, 4) if total_deals else 0,
            "lost_rate": round(lost_deals / total_deals, 4) if total_deals else 0,
            "revenue_rub": _rub(stats[4] if stats else 0),
            "avg_deal_rub": _rub((stats[4] or 0) / max(1, won_deals) if stats else 0),
            "date_from": _iso(stats[5]) if stats else None,
            "date_to": _iso(stats[6]) if stats else None,
            "pipeline_count": int(stats[7] or 0) if stats else 0,
            "manager_count": int(stats[8] or 0) if stats else 0,
        },
        "monthly_revenue": [
            {
                "month": _iso(row[0]),
                "deals": int(row[1] or 0),
                "won_deals": int(row[2] or 0),
                "lost_deals": int(row[3] or 0),
                "revenue_rub": _rub(row[4]),
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
                "deals": int(row[2] or 0),
                "revenue_rub": _rub(row[3]),
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
        "manager_metrics": manager_metrics,
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
    }


@router.get("/crm/connections/{connection_id}/dashboard-builder")
async def get_dashboard_builder(
    connection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    conn = await _resolve_conn(session, user, connection_id)
    dashboard = await _ensure_dashboard(session, conn, user)
    widgets = await _dashboard_widgets(session, dashboard.id)
    active_share = await _active_share(session, dashboard.id)
    return _serialize_dashboard(dashboard, widgets, active_share)


@router.put("/crm/connections/{connection_id}/dashboard-builder")
async def save_dashboard_builder(
    connection_id: uuid.UUID,
    payload: DashboardBuilderSaveIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    conn = await _resolve_conn(session, user, connection_id)
    dashboard = await _ensure_dashboard(session, conn, user)
    dashboard.name = payload.name[:120] or "Основной дашборд"
    dashboard.filters = payload.filters if isinstance(payload.filters, dict) else {}
    current_pages = _dashboard_pages(dashboard)
    pages = _normalize_pages(payload.pages, default_to_full=True) if payload.pages else current_pages
    page_keys = {page["page_key"] for page in pages}
    default_page_key = pages[0]["page_key"] if pages else "main"
    metadata = dashboard.metadata_json if isinstance(dashboard.metadata_json, dict) else {}
    dashboard.metadata_json = {**metadata, "pages": pages}
    dashboard.updated_at = datetime.now(timezone.utc)

    await session.execute(delete(DashboardWidget).where(DashboardWidget.dashboard_id == dashboard.id))
    for idx, item in enumerate(payload.widgets[:40]):
        clean = _clean_widget(item, idx, page_keys=page_keys, default_page_key=default_page_key)
        session.add(DashboardWidget(dashboard_id=dashboard.id, **clean))
    await session.commit()
    await session.refresh(dashboard)

    widgets = await _dashboard_widgets(session, dashboard.id)
    active_share = await _active_share(session, dashboard.id)
    return _serialize_dashboard(dashboard, widgets, active_share)


@router.post("/crm/connections/{connection_id}/dashboard-builder/share")
async def create_dashboard_share(
    connection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    conn = await _resolve_conn(session, user, connection_id)
    dashboard = await _ensure_dashboard(session, conn, user)
    now = datetime.now(timezone.utc)
    await session.execute(
        update(DashboardShare)
        .where(DashboardShare.dashboard_id == dashboard.id)
        .where(DashboardShare.status == "active")
        .values(status="revoked", revoked_at=now, updated_at=now)
    )
    share_token = _new_share_token()
    share = DashboardShare(
        dashboard_id=dashboard.id,
        token_hash=hash_share_token(share_token),
        status="active",
        created_by_user_id=user.id,
    )
    session.add(share)
    await session.commit()
    await session.refresh(share)
    widgets = await _dashboard_widgets(session, dashboard.id)
    return _serialize_dashboard(dashboard, widgets, share, share_url=_share_url(share_token))


@router.post("/crm/connections/{connection_id}/dashboard-builder/share/revoke")
async def revoke_dashboard_share(
    connection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    conn = await _resolve_conn(session, user, connection_id)
    dashboard = await _ensure_dashboard(session, conn, user)
    now = datetime.now(timezone.utc)
    await session.execute(
        update(DashboardShare)
        .where(DashboardShare.dashboard_id == dashboard.id)
        .where(DashboardShare.status == "active")
        .values(status="revoked", revoked_at=now, updated_at=now)
    )
    await session.commit()
    widgets = await _dashboard_widgets(session, dashboard.id)
    return _serialize_dashboard(dashboard, widgets, None)


@router.get("/dashboard-shares/{share_token}")
async def get_public_dashboard_share(
    share_token: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    token_hash = hash_share_token(share_token)
    row = (
        await session.execute(
            select(DashboardShare, Dashboard, CrmConnection)
            .join(Dashboard, Dashboard.id == DashboardShare.dashboard_id)
            .join(CrmConnection, CrmConnection.id == Dashboard.crm_connection_id)
            .where(DashboardShare.token_hash == token_hash)
            .where(DashboardShare.status == "active")
            .where(Dashboard.status == "active")
            .limit(1)
        )
    ).first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Dashboard share not found"}},
        )

    share, dashboard, conn = row
    widgets = await _dashboard_widgets(session, dashboard.id)
    sales = await _build_sales_snapshot(session, conn, dashboard)
    now = datetime.now(timezone.utc)
    share.last_accessed_at = now
    share.updated_at = now
    await session.commit()
    return {
        **_serialize_dashboard(dashboard, widgets, share),
        "sales": sales,
        "embed": True,
    }
