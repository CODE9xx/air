from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_billing_panel_shows_pricing_and_token_catalog():
    panel = (
        ROOT / "apps/web/components/cabinet/BillingPanel.tsx"
    ).read_text(encoding="utf-8")
    pricing = (ROOT / "apps/web/lib/pricing.ts").read_text(encoding="utf-8")

    assert "pricingPlans" in panel
    assert "aiTokenRates" in panel
    assert "topUpPacks" in panel
    assert "launchServices" in panel
    assert "Старт" in pricing
    assert "Команда" in pricing
    assert "Про" in pricing
    assert "3000" in pricing
    assert "18000" in pricing
    assert "1.5" in pricing
    assert "0.5" in pricing
