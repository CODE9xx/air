from __future__ import annotations

from pathlib import Path


def test_sidebar_has_direct_connection_dashboard_link():
    source = Path("apps/web/components/cabinet/Sidebar.tsx").read_text()
    ru = Path("apps/web/messages/ru.json").read_text()
    en = Path("apps/web/messages/en.json").read_text()

    assert "analyticsDashboard" in ru
    assert "analyticsDashboard" in en
    assert "dashboardHref" in source
    assert "/dashboard" in source
    assert "/workspaces/${workspaceId}/crm/connections" in source
