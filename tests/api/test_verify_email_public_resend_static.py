from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_public_verify_email_resend_endpoint_exists_and_is_safe():
    auth = (ROOT / "apps/api/app/auth/router.py").read_text(encoding="utf-8")
    schemas = (ROOT / "apps/api/app/auth/schemas.py").read_text(encoding="utf-8")

    assert "class VerifyEmailResendRequest" in schemas
    assert '@router.post(\n    "/verify-email/resend"' in auth
    assert "async def verify_email_resend(" in auth
    assert "VerifyEmailResendRequest" in auth
    resend_section = auth.split("async def verify_email_resend(", 1)[1].split('@router.post("/verify-email/confirm")', 1)[0]
    assert "get_current_user" not in resend_section
    assert "auth_verify_resend_email" in resend_section
    assert "limit=3" in resend_section
    assert "window_seconds=600" in resend_section
    assert "hash_secret(code)" in resend_section
    assert "send_verification_code(user.email, code, \"email_verify\")" in resend_section
    assert "return Response(status_code=status.HTTP_204_NO_CONTENT)" in resend_section


def test_public_verify_email_confirm_by_email_stays_available():
    auth = (ROOT / "apps/api/app/auth/router.py").read_text(encoding="utf-8")
    schemas = (ROOT / "apps/api/app/auth/schemas.py").read_text(encoding="utf-8")

    assert "class VerifyEmailWithEmailRequest" in schemas
    assert '@router.post("/verify-email")' in auth
    assert "VerifyEmailWithEmailRequest" in auth
    assert "auth_verify_email" in auth
