from __future__ import annotations

import inspect
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_dashboard_builder_models_and_migration_exist():
    models = (ROOT / "apps/api/app/db/models/__init__.py").read_text(encoding="utf-8")
    migration = (
        ROOT / "apps/api/app/db/migrations/main/versions/0006_dashboard_builder.py"
    ).read_text(encoding="utf-8")

    assert "class Dashboard(" in models
    assert "class DashboardWidget(" in models
    assert "class DashboardShare(" in models
    assert "dashboard_shares" in migration
    assert "token_hash" in migration
    assert "share_token" not in migration


def test_dashboard_builder_router_exposes_safe_embed_share_contract():
    source = (ROOT / "apps/api/app/dashboards/builder.py").read_text(encoding="utf-8")

    assert "/crm/connections/{connection_id}/dashboard-builder" in source
    assert "/dashboard-builder/share" in source
    assert "/dashboard-builder/share/revoke" in source
    assert "/dashboard-shares/{share_token}" in source
    assert "hash_share_token" in source
    assert "token_hash" in source
    assert "access_token_encrypted" not in source
    assert "refresh_token_encrypted" not in source


def test_dashboard_builder_supports_pages_without_new_schema():
    source = (ROOT / "apps/api/app/dashboards/builder.py").read_text(encoding="utf-8")
    migration_names = "\n".join(
        path.name
        for path in (ROOT / "apps/api/app/db/migrations/main/versions").glob("*.py")
    )

    assert "DEFAULT_PAGES" in source
    assert "DashboardPageIn" in source
    assert "metadata_json" in source
    assert "page_key" in source
    assert '"pages"' in source
    assert "dashboard_pages" not in migration_names


def test_dashboard_builder_catalog_has_groups_and_phase2b_placeholders():
    source = (ROOT / "apps/api/app/dashboards/builder.py").read_text(encoding="utf-8")

    for group in ("kpi", "dynamics", "pipelines", "managers", "risks", "phase2b"):
        assert f'"group": "{group}"' in source
    for widget_type in (
        "kpi_open",
        "kpi_avg_deal",
        "status_structure",
        "open_age_buckets",
        "pipeline_health",
        "manager_risk",
        "phase2b_calls",
    ):
        assert widget_type in source


def test_public_embed_snapshot_includes_extended_safe_metrics():
    source = (ROOT / "apps/api/app/dashboards/builder.py").read_text(encoding="utf-8")

    for metric in (
        "status_breakdown",
        "sales_cycle",
        "open_age_buckets",
        "pipeline_health",
        "manager_risk",
    ):
        assert metric in source


def test_universal_analytics_models_and_migration_exist():
    models = (ROOT / "apps/api/app/db/models/__init__.py").read_text(encoding="utf-8")
    migration = (
        ROOT / "apps/api/app/db/migrations/main/versions/0007_universal_analytics_catalog.py"
    ).read_text(encoding="utf-8")

    assert "class CrmFieldMapping(" in models
    assert "class DashboardTemplate(" in models
    assert "class AiTenantInsight(" in models
    assert "crm_field_mappings" in migration
    assert "dashboard_templates" in migration
    assert "ai_tenant_insights" in migration
    assert "access_token" not in migration
    assert "refresh_token" not in migration


def test_universal_analytics_catalog_has_80_plus_widgets_templates_and_requirements():
    source = (ROOT / "apps/api/app/dashboards/builder.py").read_text(encoding="utf-8")

    assert "UNIVERSAL_ANALYTICS_WIDGET_COUNT" in source
    assert "DASHBOARD_TEMPLATES" in source
    assert "availability" in source
    assert "requires_mapping" in source
    assert "requires_integration" in source
    assert "requires_ai" in source
    for widget_type in (
        "kpi_plan_revenue",
        "finance_paid_amount",
        "finance_debt_amount",
        "counterparty_top_paid",
        "marketing_source_revenue",
        "tasks_overdue",
        "calls_duration_by_manager",
        "messages_response_sla",
        "ai_script_adherence",
        "ai_objection_reasons",
    ):
        assert widget_type in source
    for template_key in (
        "sales_leads",
        "revenue_avg_check",
        "counterparties",
        "calls",
        "ai_quality",
        "owner_risks",
    ):
        assert template_key in source


def test_sales_dashboard_hides_system_pipelines_and_returns_manager_metrics():
    from app.dashboards import router

    source = inspect.getsource(router)

    for hidden in ("Корзина", "План", "Тендера", "Hunter"):
        assert hidden in source
    assert "hidden_pipeline" in source
    assert "manager_metrics" in source
    assert "calls_in" in source
    assert "emails_sent" in source


def test_embed_caddy_policy_allows_amocrm_without_unframing_whole_site():
    caddy = (ROOT / "deploy/caddy/code9.caddy").read_text(encoding="utf-8")

    assert "@embed path /embed/* /ru/embed/* /en/embed/* /es/embed/*" in caddy
    assert "frame-ancestors https://*.amocrm.ru https://*.kommo.com" in caddy
    assert "@notEmbed" in caddy
    assert "frame-ancestors 'none'" in caddy
