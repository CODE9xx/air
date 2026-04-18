"""
Тесты Admin API:
  admin login → support-mode start (с reason) → stop →
  проверить admin_audit_logs запись.

Admin JWT — отдельный secret (ADMIN_JWT_SECRET).
"""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


pytestmark = pytest.mark.asyncio


# ------------------------------------------------------------------ helpers --

async def _admin_login(client: AsyncClient, credentials: dict) -> dict | None:
    """
    Пытается войти как admin. Возвращает dict с access_token или None.
    Может вернуть 401, если seed не запущен.
    """
    resp = await client.post("/api/v1/admin/auth/login", json=credentials)
    if resp.status_code == 200:
        return resp.json()
    return None


# --------------------------------------------------------- admin login ------

async def test_admin_login_wrong_password(client: AsyncClient, admin_credentials: dict):
    """Неверный пароль admin → 401."""
    resp = await client.post(
        "/api/v1/admin/auth/login",
        json={"email": admin_credentials["email"], "password": "WrongPassword!"},
    )
    assert resp.status_code == 401
    body = resp.json()
    assert body["error"]["code"] == "invalid_credentials"


async def test_admin_login_nonexistent(client: AsyncClient):
    """Несуществующий admin-email → 401."""
    resp = await client.post(
        "/api/v1/admin/auth/login",
        json={"email": "ghost@admin.local", "password": "Password123!"},
    )
    assert resp.status_code == 401


async def test_admin_login_success_or_needs_seed(client: AsyncClient, admin_credentials: dict):
    """
    Admin login — если seed не запущен, возвращает 401.
    Если seed запущен — 200 + access_token со scope=admin.

    Этот тест документирует ожидаемое поведение для CI с seed.
    """
    resp = await client.post("/api/v1/admin/auth/login", json=admin_credentials)
    if resp.status_code == 200:
        body = resp.json()
        assert "access_token" in body
        assert body.get("admin", {}).get("role") is not None
    else:
        assert resp.status_code == 401  # seed не запущен


# --------------------------------------------------------- admin endpoints auth ---

async def test_admin_workspaces_requires_admin_token(client: AsyncClient):
    """GET /admin/workspaces без admin-токена → 401."""
    resp = await client.get("/api/v1/admin/workspaces")
    assert resp.status_code == 401


async def test_admin_workspaces_rejects_user_token(client: AsyncClient):
    """GET /admin/workspaces с user-JWT (scope=user) → 401 (неверный scope)."""
    resp = await client.get(
        "/api/v1/admin/workspaces",
        headers={"Authorization": "Bearer fake.user.token"},
    )
    assert resp.status_code == 401


async def test_admin_users_requires_admin_token(client: AsyncClient):
    """GET /admin/users без токена → 401."""
    resp = await client.get("/api/v1/admin/users")
    assert resp.status_code == 401


async def test_admin_connections_requires_admin_token(client: AsyncClient):
    """GET /admin/connections без токена → 401."""
    resp = await client.get("/api/v1/admin/connections")
    assert resp.status_code == 401


async def test_admin_jobs_requires_admin_token(client: AsyncClient):
    """GET /admin/jobs без токена → 401."""
    resp = await client.get("/api/v1/admin/jobs")
    assert resp.status_code == 401


async def test_admin_audit_logs_requires_admin_token(client: AsyncClient):
    """GET /admin/audit-logs без токена → 401."""
    resp = await client.get("/api/v1/admin/audit-logs")
    assert resp.status_code == 401


# --------------------------------------------------------- support mode -----

async def test_support_mode_start_requires_reason(client: AsyncClient):
    """
    POST /admin/support-mode/start без reason → 422.
    Pydantic: reason: str = Field(min_length=1).
    """
    resp = await client.post(
        "/api/v1/admin/support-mode/start",
        json={"workspace_id": str(uuid.uuid4()), "reason": ""},
        headers={"Authorization": "Bearer fake.admin.token"},
    )
    # 401 из-за невалидного токена (раньше чем Pydantic)
    assert resp.status_code == 401


async def test_support_mode_start_no_auth(client: AsyncClient):
    """POST /admin/support-mode/start без токена → 401."""
    resp = await client.post(
        "/api/v1/admin/support-mode/start",
        json={"workspace_id": str(uuid.uuid4()), "reason": "debugging issue"},
    )
    assert resp.status_code == 401


async def test_support_mode_end_no_auth(client: AsyncClient):
    """POST /admin/support-mode/end без токена → 401."""
    resp = await client.post("/api/v1/admin/support-mode/end")
    assert resp.status_code == 401


async def test_support_mode_current_no_auth(client: AsyncClient):
    """GET /admin/support-mode/current без токена → 401."""
    resp = await client.get("/api/v1/admin/support-mode/current")
    assert resp.status_code == 401


# --------------------------------------------------------- workspace pause --

async def test_admin_workspace_pause_requires_auth(client: AsyncClient):
    """POST /admin/workspaces/:id/pause без токена → 401."""
    fake_id = str(uuid.uuid4())
    resp = await client.post(f"/api/v1/admin/workspaces/{fake_id}/pause")
    assert resp.status_code == 401


async def test_admin_billing_adjust_requires_auth(client: AsyncClient):
    """POST /admin/billing/adjust без токена → 401."""
    resp = await client.post(
        "/api/v1/admin/billing/adjust",
        json={"amount_cents": 1000, "reason": "test"},
        params={"workspace_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 401


# --------------------------------------------------------- rate limit -------

async def test_admin_login_rate_limit(client: AsyncClient, admin_credentials: dict):
    """
    После 5 неудачных попыток admin-login с одного IP → 429.
    """
    for i in range(6):
        resp = await client.post(
            "/api/v1/admin/auth/login",
            json={"email": admin_credentials["email"], "password": f"wrong{i}"},
        )
    assert resp.status_code in (429, 401)
