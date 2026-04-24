from __future__ import annotations

import inspect


def test_mark_job_succeeded_preserves_existing_progress_result():
    from worker.jobs import _common

    source = inspect.getsource(_common.mark_job_succeeded)

    assert "COALESCE(result, '{}'::jsonb)" in source
    assert "|| CAST(:res AS JSONB)" in source
