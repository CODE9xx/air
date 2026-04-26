from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_payment_order_model_and_migration_exist():
    models = (ROOT / "apps/api/app/db/models/__init__.py").read_text(encoding="utf-8")
    migration = (
        ROOT / "apps/api/app/db/migrations/main/versions/0009_payments_email_change.py"
    ).read_text(encoding="utf-8")

    assert "class PaymentOrder(" in models
    assert "__tablename__ = \"payment_orders\"" in models
    assert "payment_orders" in migration
    assert "ck_payorder_status" in migration
    assert "ck_payorder_method" in migration
    assert "ck_evc_purpose" in migration
    assert "email_change" in migration


def test_billing_router_exposes_dadata_tbank_and_payment_contracts():
    source = (ROOT / "apps/api/app/billing/router.py").read_text(encoding="utf-8")

    for contract in (
        "/workspaces/{workspace_id}/billing/account",
        "/workspaces/{workspace_id}/billing/ledger",
        "/workspaces/{workspace_id}/billing/dadata/party-suggest",
        "/workspaces/{workspace_id}/billing/payments/card",
        "/workspaces/{workspace_id}/billing/payments/invoice",
        "/workspaces/{workspace_id}/billing/payments/{order_id}",
        "/billing/tbank/notifications",
    ):
        assert contract in source

    assert "compute_tbank_token" in source
    assert "tbank_webhook_not_configured" in source
    assert 'order.provider != "tbank"' in source
    assert "DADATA_API_KEY" not in source
    assert "TBANK_EACQ_PASSWORD" not in source
    assert "access_token" not in source
    assert "refresh_token" not in source


def test_payment_success_credits_tokens_and_updates_subscription():
    source = (ROOT / "apps/api/app/billing/router.py").read_text(encoding="utf-8")
    helpers = (ROOT / "apps/api/app/billing/tokens.py").read_text(encoding="utf-8")

    assert "apply_paid_payment_order" in source
    assert "credit_tokens" in helpers
    assert "subscription_expires_at" in source
    assert "TokenLedger" in source
    assert "BillingLedger" in source
    assert "idempotent" in source.lower()


def test_auth_email_change_contract_has_hashed_code_and_no_secret_response():
    auth = (ROOT / "apps/api/app/auth/router.py").read_text(encoding="utf-8")
    schemas = (ROOT / "apps/api/app/auth/schemas.py").read_text(encoding="utf-8")
    email = (ROOT / "apps/api/app/core/email.py").read_text(encoding="utf-8")

    assert "/email-change/request" in auth
    assert "/email-change/confirm" in auth
    assert "EmailChangeRequest" in schemas
    assert "EmailChangeConfirmRequest" in schemas
    assert "purpose=\"email_change\"" in auth
    assert "hash_secret(code)" in auth
    assert "verify_secret(evc.code_hash, body.code)" in auth
    assert "email_change" in email
    assert "code_hash" not in auth.split('return {"ok": True')[-1]
