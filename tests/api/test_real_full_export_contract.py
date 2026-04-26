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


def test_export_options_have_live_amocrm_fallback_for_empty_tenant_cache():
    from app.crm import router as crm_router

    src = inspect.getsource(crm_router.export_options)
    fallback_src = inspect.getsource(crm_router._live_amocrm_export_options)

    assert "run_in_threadpool(_live_amocrm_export_options, conn)" in src
    assert "connector.fetch_pipelines(access_token)" in fallback_src
    assert "connector.fetch_stages(access_token)" in fallback_src
    assert '"source": "amocrm_live"' in fallback_src


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
