from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_password_reset_ui_supports_resend_and_email_carryover():
    forgot = (ROOT / "apps/web/components/forms/ForgotPasswordForm.tsx").read_text(encoding="utf-8")
    reset = (ROOT / "apps/web/components/forms/ResetPasswordForm.tsx").read_text(encoding="utf-8")
    page = (ROOT / "apps/web/app/[locale]/reset-password/page.tsx").read_text(encoding="utf-8")

    assert "/auth/password-reset/request" in forgot
    assert "encodeURIComponent(email)" in forgot
    assert "reset-password${email" in forgot

    assert "useSearchParams" in reset
    assert "searchParams.get('email')" in reset
    assert "/auth/password-reset/request" in reset
    assert "resendCode" in reset
    assert "trim().toLowerCase()" in reset
    assert "Suspense" in page
    assert "<ResetPasswordForm />" in page


def test_password_reset_resend_messages_exist_for_all_locales():
    for locale in ("ru", "en", "es"):
        data = json.loads((ROOT / f"apps/web/messages/{locale}.json").read_text(encoding="utf-8"))
        reset = data["auth"]["resetPassword"]
        for key in ("emailHint", "resend", "resending", "resent"):
            assert reset[key]
