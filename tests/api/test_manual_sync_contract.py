from __future__ import annotations

import inspect


def test_manual_sync_rejects_duplicate_pull_jobs_before_enqueue():
    from app.crm import router

    source = inspect.getsource(router.sync_connection)

    assert "_active_pull_job_count" in source
    assert "sync_already_running" in source


def test_full_export_rejects_duplicate_pull_jobs_before_token_reservation():
    from app.crm import router

    source = inspect.getsource(router.full_export)
    reservation_index = source.index("reserve_tokens_for_export_job")
    duplicate_guard_index = source.index("_active_pull_job_count")

    assert duplicate_guard_index < reservation_index
    assert "sync_already_running" in source
