from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LANDING = ROOT / "apps/web/content/marketing/landing.html"
PRICING = ROOT / "apps/web/content/marketing/pricing.html"
CABINET_LAYOUT = ROOT / "apps/web/app/[locale]/app/layout.tsx"
SIDEBAR = ROOT / "apps/web/components/cabinet/Sidebar.tsx"
TOPBAR = ROOT / "apps/web/components/cabinet/Topbar.tsx"


def test_marketing_pages_have_mobile_overflow_guards() -> None:
    for path in (LANDING, PRICING):
        source = path.read_text(encoding="utf-8")
        assert "Mobile fit pass" in source
        assert "overflow-x: clip" in source
        assert "max-width: 100%" in source
        assert "@media (max-width: 640px)" in source


def test_cabinet_shell_stacks_on_mobile() -> None:
    layout = CABINET_LAYOUT.read_text(encoding="utf-8")
    sidebar = SIDEBAR.read_text(encoding="utf-8")
    topbar = TOPBAR.read_text(encoding="utf-8")

    assert "flex-col md:flex-row" in layout
    assert "p-4 sm:p-6" in layout
    assert "w-full" in sidebar
    assert "md:w-60" in sidebar
    assert "overflow-x-auto" in sidebar
    assert "flex-col" in topbar
    assert "sm:flex-row" in topbar
