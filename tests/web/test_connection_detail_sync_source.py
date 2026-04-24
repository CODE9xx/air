from __future__ import annotations

from pathlib import Path


def test_connection_detail_has_manual_incremental_sync_control():
    page = Path("apps/web/app/[locale]/app/connections/[id]/page.tsx").read_text()
    ru = Path("apps/web/messages/ru.json").read_text()
    en = Path("apps/web/messages/en.json").read_text()

    assert "startIncrementalSync" in page
    assert "/sync`" in page
    assert "sync_already_running" in page
    assert "syncNow" in ru
    assert "syncNow" in en
