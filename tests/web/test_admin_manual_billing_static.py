from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_admin_workspace_page_has_manual_tariff_and_token_controls():
    page = (ROOT / "apps/web/app/[locale]/admin/workspaces/page.tsx").read_text(
        encoding="utf-8"
    )

    assert "/admin/workspaces/${editingWorkspace.id}/manual-billing" in page
    assert "period_months" in page
    assert "add_tokens" in page
    assert "manualPlan" in page
    assert "subscription_expires_at" in page
    assert "Тариф/токены" in page
