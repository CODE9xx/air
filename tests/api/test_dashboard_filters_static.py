from __future__ import annotations

import inspect


def test_sales_dashboard_accepts_period_and_single_pipeline_filters():
    from app.dashboards import router

    source = inspect.getsource(router)
    sales = inspect.getsource(router.dashboard_sales)

    assert "/crm/connections/{connection_id}/dashboard/options" in source
    assert "pipeline_id: str | None = None" in sales
    assert "period: str | None = None" in sales
    assert "_dashboard_filter_state" in sales
    assert "pipeline_not_in_export" in source


def test_sales_dashboard_exposes_effective_filters():
    from app.dashboards import router

    sales = inspect.getsource(router.dashboard_sales)

    assert '"pipeline_id": filters.get("pipeline_id")' in sales
    assert '"active_pipeline_ids": filters.get("active_pipeline_ids")' in sales
    assert "_dashboard_filters(conn, filters=filters)" in sales
    assert "_dashboard_deal_join_filters(conn, filters=filters)" in sales
