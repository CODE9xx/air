from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_global_notes_import_is_disabled_by_default():
    source = (ROOT / "apps/worker/worker/jobs/crm_pull.py").read_text(encoding="utf-8")

    assert 'AMOCRM_GLOBAL_NOTES_ENABLED = os.getenv("AMOCRM_GLOBAL_NOTES_ENABLED", "false")' in source
    assert "if AMOCRM_GLOBAL_NOTES_ENABLED:" in source
    assert 'notes_skipped_reason = "global_notes_disabled"' in source
    assert "amocrm_global_notes_import_skipped" in source


def test_timeline_messages_import_is_disabled_by_default():
    source = (ROOT / "apps/worker/worker/jobs/crm_pull.py").read_text(encoding="utf-8")

    assert 'AMOCRM_TIMELINE_MESSAGES_ENABLED", "false"' in source
    assert "if AMOCRM_TIMELINE_MESSAGES_ENABLED:" in source
    assert '"skipped_reason": "timeline_messages_disabled"' in source


def test_pull_job_accepts_api_export_estimate_payload_key():
    source = (ROOT / "apps/worker/worker/jobs/crm_pull.py").read_text(encoding="utf-8")

    assert "export_estimate: dict[str, Any] | None = None" in source
    assert "enqueue passes payload keys as kwargs" in source
