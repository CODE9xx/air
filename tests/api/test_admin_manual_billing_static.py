from __future__ import annotations

import inspect


def test_admin_manual_billing_endpoint_is_superadmin_only_and_audited():
    from app.admin import router

    source = inspect.getsource(router.admin_workspace_manual_billing)

    assert '"/workspaces/{workspace_id}/manual-billing"' in inspect.getsource(router)
    assert 'require_admin_role("superadmin")' in source
    assert "credit_tokens(" in source
    assert "PLAN_MONTHLY_TOKENS" in source
    assert "subscription_expires_at" in source
    assert "AdminAuditLog(" in source
    assert 'action="workspace_manual_billing_update"' in source


def test_admin_workspace_list_returns_subscription_expiry():
    from app.admin import router

    source = inspect.getsource(router.admin_workspaces)

    assert "ta.subscription_expires_at" in source
    assert '"subscription_expires_at"' in source
