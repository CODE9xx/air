from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_connection_detail_checks_token_quote_before_full_export():
    src = (
        ROOT / "apps/web/app/[locale]/app/connections/[id]/page.tsx"
    ).read_text(encoding="utf-8")

    assert "/crm/connections/${conn.id}/full-export/quote" in src
    assert "exportQuote" in src
    assert "missing_tokens" in src
    assert "can_start" in src
    assert "Пополнить баланс" in src


def test_billing_panel_shows_token_balance_and_ledger():
    src = (ROOT / "apps/web/components/cabinet/BillingPanel.tsx").read_text(
        encoding="utf-8"
    )

    assert "/workspaces/${workspaceId}/billing/token-account" in src
    assert "/workspaces/${workspaceId}/billing/token-ledger" in src
    assert "available_tokens" in src
    assert "История токенов" in src
