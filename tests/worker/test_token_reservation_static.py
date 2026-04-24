from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_crm_pull_finalizes_token_reservations():
    crm_pull = (ROOT / "apps/worker/worker/jobs/crm_pull.py").read_text(encoding="utf-8")
    common = (ROOT / "apps/worker/worker/jobs/_common.py").read_text(encoding="utf-8")

    assert "charge_token_reservation_for_job" in crm_pull
    assert "release_token_reservation_for_job" in crm_pull
    assert "token_reservations" in common
    assert "token_ledger" in common
