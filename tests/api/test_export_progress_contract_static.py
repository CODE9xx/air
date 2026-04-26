from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CRM_ROUTER = ROOT / "apps/api/app/crm/router.py"
JOBS_ROUTER = ROOT / "apps/api/app/jobs/router.py"
CRM_PULL = ROOT / "apps/worker/worker/jobs/crm_pull.py"


def test_full_export_payload_carries_safe_eta_estimate() -> None:
    source = CRM_ROUTER.read_text(encoding="utf-8")

    assert '"export_estimate"' in source
    assert '"duration_seconds"' in source
    assert '"records"' in source
    assert "estimated_duration_seconds" in source
    assert "estimated_records" in source


def test_job_endpoint_serializes_queue_position_and_eta() -> None:
    source = JOBS_ROUTER.read_text(encoding="utf-8")

    assert "queue_position" in source
    assert "jobs_ahead" in source
    assert "estimated_remaining_seconds" in source
    assert "Queue(j.queue" in source


def test_crm_pull_updates_live_entity_counters() -> None:
    source = CRM_PULL.read_text(encoding="utf-8")

    assert "companies_imported" in source
    assert "contacts_imported" in source
    assert "deals_imported" in source
    assert "_report_stage_items" in source
