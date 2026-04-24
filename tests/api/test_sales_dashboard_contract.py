from __future__ import annotations

import inspect


def test_sales_dashboard_endpoint_returns_datalens_style_sections():
    from app.dashboards import router

    source = inspect.getsource(router)
    assert "/crm/connections/{connection_id}/dashboard/sales" in source
    assert "monthly_revenue" in source
    assert "pipeline_breakdown" in source
    assert "manager_leaderboard" in source
    assert "top_deals" in source


def test_sales_dashboard_uses_active_export_filters():
    from app.dashboards import router

    source = inspect.getsource(router.dashboard_sales)
    assert "_dashboard_filters(conn)" in source
    assert "_dashboard_deal_join_filters(conn)" in source
