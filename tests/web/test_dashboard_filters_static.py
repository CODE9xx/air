from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_connection_dashboard_has_period_and_pipeline_controls():
    page = (ROOT / "apps/web/app/[locale]/app/connections/[id]/dashboard/page.tsx").read_text(
        encoding="utf-8"
    )
    ru = (ROOT / "apps/web/messages/ru.json").read_text(encoding="utf-8")

    assert "/dashboard/options" in page
    assert "pipeline_id" in page
    assert "last_12_months" in page
    assert "all_time" in page
    assert "analyticsPipelineHint" in ru
    assert "не склеивает все вместе" in ru
