from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch


def test_amocrm_fetch_deals_sends_created_at_and_pipeline_filters():
    from crm_connectors.amocrm import AmoCrmConnector

    captured: dict[str, object] = {}

    def fake_paginated_get(path, access_token, *, items_key, params=None, page_limit=250):
        captured["path"] = path
        captured["access_token"] = access_token
        captured["items_key"] = items_key
        captured["params"] = params
        return iter(())

    connector = AmoCrmConnector(client_id="cid", client_secret="secret", subdomain="demo")
    with patch.object(connector, "_paginated_get", side_effect=fake_paginated_get):
        list(
            connector.fetch_deals(
                "token",
                created_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
                created_to=datetime(2025, 12, 31, 23, 59, 59, tzinfo=timezone.utc),
                pipeline_ids=["111", "222"],
            )
        )

    assert captured["path"] == "leads"
    assert captured["items_key"] == "leads"
    assert captured["access_token"] == "token"
    assert captured["params"] == {
        "with": "contacts,companies",
        "filter[created_at][from]": 1735689600,
        "filter[created_at][to]": 1767225599,
        "filter[pipeline_id][0]": "111",
        "filter[pipeline_id][1]": "222",
    }


def test_amocrm_paginated_get_retries_transient_request_errors(monkeypatch):
    import httpx

    from crm_connectors.amocrm import AmoCrmConnector

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"_embedded": {"leads": [{"id": 123}]}, "_links": {}}

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout
            self.calls = 0

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise httpx.RemoteProtocolError("server disconnected")
            return FakeResponse()

    fake_client = FakeClient(timeout=30)
    monkeypatch.setattr("crm_connectors.amocrm.httpx.Client", lambda timeout: fake_client)
    monkeypatch.setattr("crm_connectors.amocrm.time.sleep", lambda delay: None)

    connector = AmoCrmConnector(client_id="cid", client_secret="secret", subdomain="demo")

    rows = list(connector._paginated_get("leads", "token", items_key="leads"))

    assert rows == [{"id": 123}]
    assert fake_client.calls == 2


def test_pull_amocrm_core_signature_accepts_real_export_filters():
    import inspect

    from worker.jobs.crm_pull import pull_amocrm_core

    sig = inspect.signature(pull_amocrm_core)
    for name in ("date_from_iso", "date_to_iso", "pipeline_ids", "cleanup_trial"):
        assert name in sig.parameters
        assert sig.parameters[name].kind == inspect.Parameter.KEYWORD_ONLY


def test_build_active_export_metadata_records_filter_and_counts():
    from worker.jobs.crm_pull import _build_active_export_metadata

    result = _build_active_export_metadata(
        date_from_iso="2025-01-01",
        date_to_iso="2025-12-31",
        pipeline_ids=["111", "222"],
        counts={"pipelines": 2, "stages": 7, "users": 4, "contacts": 25, "deals": 40},
    )

    assert result["mode"] == "real"
    assert result["date_basis"] == "created_at"
    assert result["date_from"] == "2025-01-01"
    assert result["date_to"] == "2025-12-31"
    assert result["pipeline_ids"] == ["111", "222"]
    assert result["counts"]["deals"] == 40
    assert result["completed_at"]


def test_active_deals_count_uses_unique_tenant_rows_with_active_filters():
    from worker.jobs.crm_pull import _tenant_active_deals_count

    class ScalarResult:
        def scalar(self):
            return 7

    class FakeSession:
        def __init__(self):
            self.calls = []

        def execute(self, statement, params=None):
            self.calls.append((str(statement), params or {}))
            return ScalarResult()

    fake_session = FakeSession()

    count = _tenant_active_deals_count(
        fake_session,
        schema="crm_amo_1225ed1d",
        created_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
        created_to=datetime(2025, 12, 31, 23, 59, 59, tzinfo=timezone.utc),
        pipeline_ids=["111", "222"],
    )

    assert count == 7
    sql, params = fake_session.calls[0]
    assert 'FROM "crm_amo_1225ed1d".deals d' in sql
    assert 'LEFT JOIN "crm_amo_1225ed1d".pipelines p ON p.id = d.pipeline_id' in sql
    assert "d.created_at_external >= :created_from" in sql
    assert "d.created_at_external <= :created_to" in sql
    assert "p.external_id IN (:active_pipeline_0, :active_pipeline_1)" in sql
    assert params["active_pipeline_0"] == "111"
    assert params["active_pipeline_1"] == "222"
