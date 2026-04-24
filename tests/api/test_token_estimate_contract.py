from __future__ import annotations


def test_token_estimate_route_exists():
    from app.crm.router import router as crm_router

    expected = "/crm/connections/{connection_id}/token-estimate"
    paths = [
        (route.path, tuple(sorted(route.methods or ())))
        for route in crm_router.routes
        if hasattr(route, "path")
    ]

    assert any(p == expected and "GET" in methods for p, methods in paths), paths


def test_build_token_estimate_uses_full_snapshot_and_call_minutes():
    from app.crm.router import _build_token_estimate

    result = _build_token_estimate(
        connection_id="conn-1",
        metadata={
            "token_estimate_snapshot": {
                "source": "manual_probe",
                "captured_at": "2026-04-24T10:00:00+00:00",
                "counts": {
                    "deals": 120_051,
                    "contacts": 28_746,
                    "companies": 3_696,
                    "lead_notes": 600_000,
                    "events": 6_005_614,
                },
                "avg_tokens": {
                    "deals": 1875,
                    "contacts": 274,
                    "companies": 402,
                    "lead_notes": 159,
                    "events": 182,
                },
                "confidence": {
                    "lead_notes": "lower_bound",
                    "events": "upper_bound",
                },
            }
        },
        call_minutes=60,
    )

    assert result["source"] == "manual_probe"
    assert result["basis"] == "full_database_snapshot"
    assert result["total_tokens_without_calls"] == 1_422_879_569
    assert result["calls"]["estimated_tokens_low"] == 21_000
    assert result["calls"]["estimated_tokens_high"] == 34_200
    assert result["total_tokens_low"] == 1_422_900_569
    assert result["total_tokens_high"] == 1_422_913_769
    assert [item["key"] for item in result["items"]] == [
        "deals",
        "contacts",
        "companies",
        "lead_notes",
        "events",
    ]


def test_build_token_estimate_falls_back_to_active_export_counts():
    from app.crm.router import _build_token_estimate

    result = _build_token_estimate(
        connection_id="conn-1",
        metadata={
            "last_pull_counts": {
                "deals": 100,
                "contacts": 25,
                "companies": 2,
            }
        },
    )

    assert result["source"] == "active_export_counts"
    assert result["basis"] == "active_export_lower_bound"
    assert result["total_tokens_without_calls"] == 195_154
