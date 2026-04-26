from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_verify_email_form_uses_public_email_code_endpoint():
    source = (ROOT / "apps/web/components/forms/VerifyEmailForm.tsx").read_text(encoding="utf-8")

    assert "api.post('/auth/verify-email'" in source
    assert "{ email, code: values.code }" in source
    assert "{ scope: 'public' }" in source
    assert "/auth/verify-email/confirm" not in source


def test_verify_email_form_can_resend_without_logged_in_session():
    source = (ROOT / "apps/web/components/forms/VerifyEmailForm.tsx").read_text(encoding="utf-8")

    assert "api.post('/auth/verify-email/resend'" in source
    assert "{ email }" in source
    assert "{ scope: 'public' }" in source
    assert "/auth/verify-email/request" not in source
