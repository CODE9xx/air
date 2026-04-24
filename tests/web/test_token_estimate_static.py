from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_connection_detail_renders_token_estimate_screen():
    src = (
        ROOT / "apps/web/app/[locale]/app/connections/[id]/page.tsx"
    ).read_text(encoding="utf-8")

    assert "/crm/connections/${conn.id}/token-estimate" in src
    assert "tokenEstimatePeriod" in src
    assert "period=${tokenEstimatePeriod}" in src
    assert "tokenEstimateAllTime" in src
    assert "tokenEstimateActiveExport" in src
    assert "TokenEstimateResponse" in src
    assert "callHours" in src
    assert "total_tokens_without_calls" in src
    assert "totalWithCallsHigh" in src
