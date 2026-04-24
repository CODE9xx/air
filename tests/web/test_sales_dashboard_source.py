from __future__ import annotations

from pathlib import Path


def test_connection_dashboard_uses_sales_dashboard_endpoint():
    page = Path("apps/web/app/[locale]/app/connections/[id]/dashboard/page.tsx").read_text()
    ru = Path("apps/web/messages/ru.json").read_text()

    assert "/dashboard/sales" in page
    assert "monthly_revenue" in page
    assert "pipeline_breakdown" in page
    assert "manager_leaderboard" in page
    assert "open_age_buckets" in page
    assert "pipeline_health" in page
    assert "manager_risk" in page
    assert "salesTitle" in ru
    assert "riskTitle" in ru
