from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
AMO = ROOT / "packages/crm-connectors/src/crm_connectors/amocrm.py"
BASE = ROOT / "packages/crm-connectors/src/crm_connectors/base.py"
CRM_PULL = ROOT / "apps/worker/worker/jobs/crm_pull.py"


def test_amocrm_connector_has_extended_read_methods() -> None:
    source = AMO.read_text(encoding="utf-8")

    assert 'def fetch_tasks(' in source
    assert 'def fetch_notes(' in source
    assert 'def fetch_events(' in source
    assert 'def fetch_products(' in source
    assert '"tasks"' in source
    assert '"leads/notes"' in source
    assert '"events"' in source
    assert '"catalogs"' in source


def test_base_contract_has_raw_event() -> None:
    source = BASE.read_text(encoding="utf-8")

    assert "class RawEvent" in source
    assert "def fetch_events(" in source
    assert '"RawEvent"' in source


def test_worker_pulls_extended_entities_after_real_export() -> None:
    source = CRM_PULL.read_text(encoding="utf-8")

    assert "raw_tasks" in source
    assert "raw_notes" in source
    assert "raw_events" in source
    assert "raw_calls" in source
    assert "raw_products" in source
    assert "deal_tags" in source
    assert "if not first_pull:" in source
    assert "tasks_processed" in source
    assert "notes_processed" in source
    assert "events_processed" in source
    assert "products_processed" in source
