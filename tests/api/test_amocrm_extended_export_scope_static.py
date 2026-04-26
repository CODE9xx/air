from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
AMO = ROOT / "packages/crm-connectors/src/crm_connectors/amocrm.py"
BASE = ROOT / "packages/crm-connectors/src/crm_connectors/base.py"
CRM_PULL = ROOT / "apps/worker/worker/jobs/crm_pull.py"
TENANT_MODELS = ROOT / "apps/api/app/db/models/tenant_schema.py"
TENANT_MIGRATION = ROOT / "apps/api/app/db/migrations/tenant/versions/0004_extended_export_scope.py"
DASHBOARD = ROOT / "apps/api/app/dashboards/router.py"
WEB_DETAIL = ROOT / "apps/web/app/[locale]/app/connections/[id]/page.tsx"


def test_tenant_schema_has_extended_export_tables() -> None:
    models = TENANT_MODELS.read_text(encoding="utf-8")
    migration = TENANT_MIGRATION.read_text(encoding="utf-8")

    for name in (
        "class DealContact",
        "class DealCompany",
        "class DealStageTransition",
        "class DealSource",
        "class CrmCustomField",
        "class CrmCustomFieldValue",
    ):
        assert name in models

    for table in (
        "deal_contacts",
        "deal_companies",
        "deal_stage_transitions",
        "deal_sources",
        "crm_custom_fields",
        "crm_custom_field_values",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in migration


def test_connector_contract_has_contact_messages_inbox_and_custom_fields() -> None:
    base = BASE.read_text(encoding="utf-8")
    amo = AMO.read_text(encoding="utf-8")

    assert "class RawCustomField" in base
    assert "def fetch_contact_timeline_messages(" in base
    assert "def fetch_inbox_chats(" in base
    assert "def fetch_custom_fields(" in base

    assert "def fetch_contact_timeline_messages(" in amo
    assert "ajax/v3/contacts/{contact_id}/events_timeline" in amo
    assert "def fetch_inbox_chats(" in amo
    assert "ajax/v4/inbox/list" in amo
    assert "def fetch_custom_fields(" in amo
    assert "custom_fields" in amo


def test_worker_builds_extended_scope_without_failing_export() -> None:
    source = CRM_PULL.read_text(encoding="utf-8")

    for symbol in (
        "_sync_deal_contacts",
        "_sync_deal_companies",
        "_sync_deal_source",
        "_sync_custom_field_values",
        "_pull_custom_fields",
        "_pull_stage_transitions",
        "_load_selected_contact_rows",
        "_pull_inbox_chats_best_effort",
        "messages_coverage",
    ):
        assert symbol in source

    for stage in (
        'stage="contacts_scope"',
        'stage="custom_fields"',
        'stage="sources"',
        'stage="stage_transitions"',
        'stage="tasks_enriched"',
    ):
        assert stage in source


def test_dashboard_uses_real_sources_messages_tasks_and_stage_metrics() -> None:
    source = DASHBOARD.read_text(encoding="utf-8")

    assert "deal_sources" in source
    assert "raw_dashboard_sources" in source
    assert "messages_response_sla" in source
    assert "deal_stage_transitions" in source
    assert "tasks_overdue" in source
    assert "tasks_no_next_step" in source


def test_connection_detail_shows_extended_export_counts() -> None:
    source = WEB_DETAIL.read_text(encoding="utf-8")

    for label in (
        "stage_transitions",
        "deal_sources",
        "custom_field_values",
        "deal_contacts",
        "messages_coverage",
    ):
        assert label in source
