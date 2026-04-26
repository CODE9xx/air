from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_dashboard_builder_page_uses_drag_grid_and_share_actions():
    page = (
        ROOT / "apps/web/app/[locale]/app/connections/[id]/dashboard-builder/page.tsx"
    ).read_text(encoding="utf-8")

    assert "react-grid-layout" in page
    assert "ResponsiveGridLayout" in page
    assert "/dashboard-builder/share" in page
    assert "shareUrl" in page
    assert "widgetCatalog" in page


def test_dashboard_builder_page_supports_pages_groups_search_and_templates():
    page = (
        ROOT / "apps/web/app/[locale]/app/connections/[id]/dashboard-builder/page.tsx"
    ).read_text(encoding="utf-8")

    assert "activePageKey" in page
    assert "pageWidgets" in page
    assert "addPage" in page
    assert "renameActivePage" in page
    assert "deleteActivePage" in page
    assert "moveActivePage" in page
    assert "groupedCatalog" in page
    assert "catalogSearch" in page
    assert "quickTemplates" in page


def test_embed_dashboard_page_is_public_read_only():
    page = (ROOT / "apps/web/app/[locale]/embed/dashboards/[token]/page.tsx").read_text(
        encoding="utf-8"
    )

    assert "/dashboard-shares/" in page
    assert "Sidebar" not in page
    assert "api.post" not in page
    assert "api.patch" not in page
    assert "api.delete" not in page
    assert "activePageKey" in page
    assert "pageWidgets" in page


def test_dashboard_widget_renderer_has_extended_catalog_widgets_and_placeholders():
    renderer = (
        ROOT / "apps/web/components/dashboard-builder/DashboardWidgetRenderer.tsx"
    ).read_text(encoding="utf-8")
    types = (ROOT / "apps/web/components/dashboard-builder/types.ts").read_text(
        encoding="utf-8"
    )

    for widget_type in (
        "kpi_open",
        "kpi_avg_deal",
        "status_structure",
        "open_age_buckets",
        "pipeline_health",
        "manager_risk",
        "phase2b_calls",
    ):
        assert widget_type in renderer
        assert widget_type in types
    assert "Данные ещё не импортированы" in renderer


def test_universal_analytics_builder_ui_exposes_availability_templates_and_setup_states():
    page = (
        ROOT / "apps/web/app/[locale]/app/connections/[id]/dashboard-builder/page.tsx"
    ).read_text(encoding="utf-8")
    renderer = (
        ROOT / "apps/web/components/dashboard-builder/DashboardWidgetRenderer.tsx"
    ).read_text(encoding="utf-8")
    types = (ROOT / "apps/web/components/dashboard-builder/types.ts").read_text(
        encoding="utf-8"
    )

    assert "availabilityFilter" in page
    assert "templateCatalog" in page
    assert "applyDashboardTemplate" in page
    assert "Нужно настроить поле" in renderer
    assert "Нужно подключить интеграцию" in renderer
    assert "Нужно включить AI-анализ" in renderer
    assert "availability" in types
    assert "requirements" in types
    assert "DashboardTemplate" in types


def test_sidebar_links_to_dashboard_builder():
    sidebar = (ROOT / "apps/web/components/cabinet/Sidebar.tsx").read_text(encoding="utf-8")
    ru = (ROOT / "apps/web/messages/ru.json").read_text(encoding="utf-8")

    assert "dashboardBuilderHref" in sidebar
    assert "dashboardBuilder" in sidebar
    assert "Конструктор" in ru
