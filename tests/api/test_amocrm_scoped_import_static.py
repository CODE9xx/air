from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CRM_PULL = ROOT / "apps/worker/worker/jobs/crm_pull.py"
CRM_ROUTER = ROOT / "apps/api/app/crm/router.py"
WEB_DETAIL = ROOT / "apps/web/app/[locale]/app/connections/[id]/page.tsx"
AMOCRM_CONNECTOR = ROOT / "packages/crm-connectors/src/crm_connectors/amocrm.py"


def test_worker_has_bounded_scoped_message_and_event_modes() -> None:
    source = CRM_PULL.read_text(encoding="utf-8")

    assert "export_scope: str | None = None" in source
    assert 'if scoped_export == "messages":' in source
    assert 'if scoped_export == "events":' in source
    assert "AMOCRM_MESSAGES_IMPORT_LIMIT_DEFAULT" in source
    assert 'AMOCRM_MESSAGES_ENTITY_LIMIT_DEFAULT = _env_int("AMOCRM_MESSAGES_ENTITY_LIMIT", 0)' in source
    assert "AMOCRM_EVENTS_IMPORT_LIMIT_DEFAULT" in source
    assert "messages_entity_limit: int | None = None" in source
    assert "message_deals_scanned" in source
    assert "timeline_entity_scan_disabled" in source
    assert "amocrm_ajax_inbox_last_message" in source
    assert "inbox_last:{chat_external_id}" in source
    assert "amocrm_messages_import" in source
    assert "amocrm_events_import" in source


def test_amocrm_timeline_import_is_best_effort_per_entity() -> None:
    source = AMOCRM_CONNECTOR.read_text(encoding="utf-8")

    assert 'f"ajax/v3/leads/{deal_id}/events_timeline"' in source
    assert 'f"ajax/v3/contacts/{contact_id}/events_timeline"' in source
    assert source.count("except ProviderError:") >= 2
    assert "selected-pipeline message import" in source


def test_api_exposes_scoped_import_endpoints_without_new_job_kind() -> None:
    source = CRM_ROUTER.read_text(encoding="utf-8")

    assert '@router.post("/connections/{connection_id}/messages-sync"' in source
    assert '@router.post("/connections/{connection_id}/events-sync"' in source
    assert "export_scope=\"messages\"" in source
    assert "export_scope=\"events\"" in source
    assert 'kind="pull_amocrm_core"' in source


def test_connection_detail_has_scoped_import_buttons() -> None:
    source = WEB_DETAIL.read_text(encoding="utf-8")

    assert "startScopedImport" in source
    assert "messages-sync" in source
    assert "events-sync" in source
    assert "importMessages" in source
    assert "importEvents" in source
