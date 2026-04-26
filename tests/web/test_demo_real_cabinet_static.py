from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

REAL_APP_PAGES = [
    ROOT / "apps/web/app/[locale]/app/page.tsx",
    ROOT / "apps/web/app/[locale]/app/connections/new/page.tsx",
    ROOT / "apps/web/app/[locale]/app/connections/[id]/audit/page.tsx",
    ROOT / "apps/web/app/[locale]/app/connections/[id]/dashboard/page.tsx",
    ROOT / "apps/web/app/[locale]/app/connections/[id]/billing/page.tsx",
    ROOT / "apps/web/app/[locale]/app/notifications/page.tsx",
    ROOT / "apps/web/app/[locale]/app/ai/page.tsx",
    ROOT / "apps/web/app/[locale]/app/knowledge-base/page.tsx",
]


def test_client_login_route_uses_real_login_form_redirecting_to_connection_setup() -> None:
    page = ROOT / "apps/web/app/[locale]/client-login/page.tsx"
    assert page.exists(), "client-login must be a real Next route, not only static demo HTML"
    source = page.read_text(encoding="utf-8")
    assert "LoginForm" in source
    assert "redirectTo={`/${locale}/app/connections/new`}" in source
    assert "useUserAuth" in source
    assert "router.replace(`/${locale}/app/connections/new`)" in source


def test_login_form_keeps_default_app_redirect_and_allows_override() -> None:
    source = (ROOT / "apps/web/components/forms/LoginForm.tsx").read_text(encoding="utf-8")
    assert "interface LoginFormProps" in source
    assert "redirectTo?: string" in source
    assert "export function LoginForm({ redirectTo }: LoginFormProps = {})" in source
    assert "api.get<User>('/auth/me')" in source
    assert "setUser(currentUser)" in source
    assert "router.push(redirectTo ?? `/${locale}/app`)" in source


def test_real_app_pages_do_not_use_ws_demo_fallback_for_api_calls() -> None:
    offenders = [
        str(path.relative_to(ROOT))
        for path in REAL_APP_PAGES
        if "ws-demo-1" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []
