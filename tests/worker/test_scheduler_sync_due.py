from __future__ import annotations

from datetime import datetime, timezone


def test_plan_cadence_seconds_maps_tariffs():
    from worker.scheduler import _plan_cadence_seconds

    assert _plan_cadence_seconds("free") == 24 * 60 * 60
    assert _plan_cadence_seconds("start") == 24 * 60 * 60
    assert _plan_cadence_seconds("team") == 60 * 60
    assert _plan_cadence_seconds("pro") == 15 * 60
    assert _plan_cadence_seconds("enterprise") == 15 * 60
    assert _plan_cadence_seconds("unknown") == 24 * 60 * 60


def test_last_pull_iso_prefers_metadata_over_last_sync_at():
    from worker.scheduler import _last_pull_iso

    last_sync_at = datetime(2026, 4, 1, tzinfo=timezone.utc)
    result = _last_pull_iso(
        {"last_pull_at": "2026-04-24T12:27:06+00:00"},
        last_sync_at,
    )

    assert result == "2026-04-24T12:27:06+00:00"


def test_last_pull_iso_falls_back_to_last_sync_at():
    from worker.scheduler import _last_pull_iso

    result = _last_pull_iso({}, datetime(2026, 4, 1, 10, 0, tzinfo=timezone.utc))

    assert result == "2026-04-01T10:00:00+00:00"
