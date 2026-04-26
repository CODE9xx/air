from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "apps/web/app/[locale]/app/connections/[id]/page.tsx"


def test_connection_detail_shows_queue_eta_and_progress_counts() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert "queue_position" in source
    assert "estimated_remaining_seconds" in source
    assert "estimated_records" in source
    assert "formatDuration" in source
    assert "formatProgressCountLabel" in source
    assert "companies_imported" in source
    assert "contacts_imported" in source
    assert "deals_imported" in source
