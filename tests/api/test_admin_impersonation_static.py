from __future__ import annotations

import inspect


def test_admin_impersonation_endpoint_is_audited_and_superadmin_only():
    from app.admin import router

    source = inspect.getsource(router)

    assert '"/support-mode/impersonate"' in source
    assert 'require_admin_role("superadmin")' in source
    assert "support_impersonation_start" in source
    assert "AdminSupportSession(" in source
    assert "support_session_id" in source
    assert "support_admin_id" in source


def test_admin_lists_return_items_for_frontend():
    from app.admin import router

    source = inspect.getsource(router)

    assert '"items": items' in source
    assert '"owner_email"' in source
    assert '"available_tokens"' in source
    assert '"error_connections"' in source
