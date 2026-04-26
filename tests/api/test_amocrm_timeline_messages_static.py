from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
AMO = ROOT / "packages/crm-connectors/src/crm_connectors/amocrm.py"
CRM_PULL = ROOT / "apps/worker/worker/jobs/crm_pull.py"
WEB_DETAIL = ROOT / "apps/web/app/[locale]/app/connections/[id]/page.tsx"


def test_amocrm_connector_has_backend_only_timeline_message_import() -> None:
    source = AMO.read_text(encoding="utf-8")

    assert "def fetch_lead_timeline_messages(" in source
    assert "ajax/v3/leads/{deal_id}/events_timeline" in source
    assert '"X-Requested-With": "XMLHttpRequest"' in source
    assert '"filter[created_at][gte_lte]"' in source


def test_worker_imports_timeline_messages_for_selected_deals() -> None:
    source = CRM_PULL.read_text(encoding="utf-8")

    assert "_load_selected_deal_rows" in source
    assert "_pull_timeline_messages" in source
    assert "raw_messages" in source
    assert "raw_chats" in source
    assert "messages_processed" in source
    assert "chats_processed" in source


def test_connection_detail_shows_message_counts() -> None:
    source = WEB_DETAIL.read_text(encoding="utf-8")

    assert "messages_imported" in source
    assert "messages_processed" in source
    assert "chats_processed" in source
