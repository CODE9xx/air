from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_real_export_attaches_active_sync_job_on_conflict():
    page = (ROOT / "apps/web/app/[locale]/app/connections/[id]/page.tsx").read_text(
        encoding="utf-8"
    )

    assert "attachActivePullJob" in page
    assert "`/crm/connections/${conn.id}/jobs`" in page
    assert "error.code === 'sync_already_running'" in page
    assert "setActiveJobKind('sync')" in page
