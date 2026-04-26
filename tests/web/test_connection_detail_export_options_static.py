from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "apps/web/app/[locale]/app/connections/[id]/page.tsx"


def test_empty_export_options_can_be_reloaded_after_initial_sync() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert "const loadExportOptions = async" in source
    assert "if (exportOptions?.pipelines.length) return;" in source
    assert "await loadExportOptions(true);" in source
    assert "if (showExportSetup)" in source
    assert "await loadExportOptions(exportOptions?.pipelines.length === 0);" in source
