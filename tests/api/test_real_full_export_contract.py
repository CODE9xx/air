from __future__ import annotations

import inspect


def test_export_options_route_exists():
    from app.crm.router import router as crm_router

    expected = "/crm/connections/{connection_id}/export/options"
    paths = [
        (route.path, tuple(sorted(route.methods or ())))
        for route in crm_router.routes
        if hasattr(route, "path")
    ]

    assert any(p == expected and "GET" in methods for p, methods in paths), paths


def test_full_export_uses_pull_amocrm_core_without_billing_gate():
    from app.crm import router as crm_router

    src = inspect.getsource(crm_router.full_export)

    assert "pull_amocrm_core" in src
    assert "build_export_zip" not in src
    assert "BillingAccount" not in src
    assert "PAYMENT_REQUIRED" not in src
    assert "balance_cents" not in src


def test_full_export_request_schema_has_filters():
    from app.crm.schemas import FullExportRequest

    fields = FullExportRequest.model_fields
    assert {"date_from", "date_to", "pipeline_ids"} <= set(fields)
