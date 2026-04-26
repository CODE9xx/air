from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_balance_page_has_card_invoice_and_dadata_flow():
    source = (ROOT / "apps/web/app/[locale]/app/balance/page.tsx").read_text(encoding="utf-8")

    assert "/billing/payments/card" in source
    assert "/billing/payments/invoice" in source
    assert "/billing/dadata/party-suggest" in source
    assert "selectedCompany" in source
    assert "window.location.assign" in source


def test_subscriptions_page_uses_real_payment_endpoint_for_card():
    source = (ROOT / "apps/web/app/[locale]/app/subscriptions/page.tsx").read_text(encoding="utf-8")

    assert "/billing/payments/card" in source
    assert "purchase_type: 'subscription'" in source
    assert "addon_keys" in source
    assert "sla_keys" in source
    assert "disabledToast" not in source


def test_settings_page_has_email_change_flow():
    source = (ROOT / "apps/web/app/[locale]/app/settings/page.tsx").read_text(encoding="utf-8")

    assert "/auth/email-change/request" in source
    assert "/auth/email-change/confirm" in source
    assert "current_password" in source
    assert "setUser" in source
