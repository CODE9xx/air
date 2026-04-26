from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_admin_workspaces_can_enter_client_cabinet():
    page = (ROOT / "apps/web/app/[locale]/admin/workspaces/page.tsx").read_text(
        encoding="utf-8"
    )
    topbar = (ROOT / "apps/web/components/cabinet/Topbar.tsx").read_text(encoding="utf-8")

    assert "/admin/support-mode/impersonate" in page
    assert "setAccessToken(res.access_token)" in page
    assert "setUser(res.user)" in page
    assert "code9_support_mode" in page
    assert "code9_support_mode" in topbar
    assert "Support mode" in topbar
