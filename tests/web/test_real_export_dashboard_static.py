from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_connection_dashboard_uses_connection_scoped_api():
    src = (
        ROOT
        / "apps/web/app/[locale]/app/connections/[id]/dashboard/page.tsx"
    ).read_text(encoding="utf-8")

    assert "/crm/connections/${id}/dashboard/overview" in src
    assert "/workspaces/${wsId}/dashboards/overview" not in src


def test_connection_detail_has_real_export_setup_flow():
    src = (
        ROOT / "apps/web/app/[locale]/app/connections/[id]/page.tsx"
    ).read_text(encoding="utf-8")

    assert "/crm/connections/${conn.id}/export/options" in src
    assert "/crm/connections/${conn.id}/full-export" in src
    assert "last12Months" in src
    assert "pipeline_ids" in src
