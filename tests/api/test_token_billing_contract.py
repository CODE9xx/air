from __future__ import annotations

from datetime import date


def test_export_token_quote_uses_full_snapshot_for_all_time():
    from app.billing.tokens import build_full_export_quote

    quote = build_full_export_quote(
        connection_id="conn-1",
        date_from=date(2000, 1, 1),
        date_to=date(2026, 4, 24),
        pipeline_ids=["1", "2"],
        metadata={
            "token_estimate_snapshot": {
                "counts": {
                    "deals": 120_051,
                    "contacts": 28_746,
                    "companies": 3_696,
                    "lead_notes": 600_000,
                    "events": 6_005_614,
                }
            }
        },
        available_mtokens=18_000_000,
        cached_deals_count=None,
    )

    assert quote["estimated_contacts"] == 28_746
    assert quote["estimated_tokens"] == 86_238
    assert quote["available_tokens"] == 18_000
    assert quote["missing_tokens"] == 68_238
    assert quote["can_start"] is False
    assert quote["line_items"][0]["unit_tokens"] == 3


def test_export_token_quote_scales_snapshot_by_cached_deal_count():
    from app.billing.tokens import build_full_export_quote

    quote = build_full_export_quote(
        connection_id="conn-1",
        date_from=date(2025, 4, 24),
        date_to=date(2026, 4, 24),
        pipeline_ids=[],
        metadata={
            "token_estimate_snapshot": {
                "counts": {
                    "deals": 120_051,
                    "contacts": 28_746,
                }
            }
        },
        available_mtokens=40_000_000,
        cached_deals_count=43_201,
    )

    assert quote["estimated_deals"] == 43_201
    assert quote["estimated_contacts"] == 10_344
    assert quote["estimated_tokens"] == 31_032
    assert quote["missing_tokens"] == 0
    assert quote["can_start"] is True


def test_full_export_quote_route_exists():
    from app.crm.router import router as crm_router

    expected = "/crm/connections/{connection_id}/full-export/quote"
    paths = [
        (route.path, tuple(sorted(route.methods or ())))
        for route in crm_router.routes
        if hasattr(route, "path")
    ]

    assert any(p == expected and "POST" in methods for p, methods in paths), paths
