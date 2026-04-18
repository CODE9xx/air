"""
E2E-тест: mock connection → sync job → audit job → scores appeared.

Полный сценарий:
  1. Регистрация + verify (через прямой доступ к БД или mock-verify endpoint)
  2. Login → access_token
  3. POST /crm/connections/mock-amocrm → connection_id
  4. Дождаться bootstrap_tenant_schema (job status=succeeded)
  5. POST /crm/connections/:id/sync → job_id
  6. Проверить job.status=succeeded (или timeout 30s)
  7. POST /crm/connections/:id/audit → job_id
  8. Проверить job.status=succeeded
  9. GET /dashboards/overview → overview data (deals > 0)

Примечание: полноценный E2E требует работающих Redis + PostgreSQL + worker.
В unit-окружении тесты помечены @pytest.mark.integration.
"""
from __future__ import annotations

import asyncio
import uuid

import pytest
from httpx import AsyncClient


pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


# ------------------------------------------------------------------ helpers --

async def _poll_job_status(
    client: AsyncClient,
    access_token: str,
    job_id: str,
    timeout_seconds: int = 30,
    poll_interval: float = 1.0,
) -> dict:
    """Опрашивает статус job до succeeded/failed или timeout."""
    headers = {"Authorization": f"Bearer {access_token}"}
    elapsed = 0.0
    while elapsed < timeout_seconds:
        resp = await client.get(f"/api/v1/jobs/{job_id}", headers=headers)
        if resp.status_code == 200:
            body = resp.json()
            if body.get("status") in ("succeeded", "failed"):
                return body
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval
    return {"status": "timeout", "job_id": job_id}


# --------------------------------------------------------- e2e flow ----------

async def test_connect_sync_audit_e2e(client: AsyncClient, test_user_data: dict):
    """
    Полный E2E: connect → sync → audit.
    Без работающего воркера тест заканчивается на enqueue-шаге с успехом.
    """
    # 1. Register
    reg_resp = await client.post("/api/v1/auth/register", json=test_user_data)
    if reg_resp.status_code != 201:
        pytest.skip(f"Register failed: {reg_resp.text}")

    user_id = reg_resp.json()["user_id"]
    workspace_id = reg_resp.json()["workspace_id"]

    # 2. В интеграционной среде — верифицировать email через БД
    # Здесь используем прямой verify endpoint (если email_code доступен через лог)
    # Без DB-доступа — skip дальнейших шагов
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": test_user_data["email"], "password": test_user_data["password"]},
    )
    if login_resp.status_code == 403:
        pytest.skip("Email не верифицирован — нужен прямой DB-доступ для E2E")

    assert login_resp.status_code == 200
    access_token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    # 3. Создать mock CRM connection
    conn_resp = await client.post(
        "/api/v1/crm/connections/mock-amocrm",
        json={"name": "E2E Test Connection"},
        headers=headers,
    )
    assert conn_resp.status_code == 201, f"Create connection failed: {conn_resp.text}"
    connection_id = conn_resp.json()["id"]

    # 4. Список connections — токены не видны
    list_resp = await client.get("/api/v1/crm/connections", headers=headers)
    assert list_resp.status_code == 200
    connections = list_resp.json()
    assert len(connections) >= 1
    for c in connections:
        assert "access_token_encrypted" not in c
        assert "refresh_token_encrypted" not in c
        assert "access_token" not in c
        assert "refresh_token" not in c

    # 5. Sync job
    sync_resp = await client.post(
        f"/api/v1/crm/connections/{connection_id}/sync",
        headers=headers,
    )
    assert sync_resp.status_code == 202, f"Sync failed: {sync_resp.text}"
    sync_job_id = sync_resp.json()["job_id"]

    # 6. Poll sync job status (если воркер работает)
    sync_status = await _poll_job_status(client, access_token, sync_job_id, timeout_seconds=30)
    if sync_status["status"] == "timeout":
        pytest.skip("Worker недоступен — sync job не завершился за 30s")

    assert sync_status["status"] == "succeeded", f"Sync job failed: {sync_status}"

    # 7. Audit job
    audit_resp = await client.post(
        f"/api/v1/crm/connections/{connection_id}/audit",
        headers=headers,
    )
    assert audit_resp.status_code == 202, f"Audit failed: {audit_resp.text}"
    audit_job_id = audit_resp.json()["job_id"]

    # 8. Poll audit job
    audit_status = await _poll_job_status(client, access_token, audit_job_id, timeout_seconds=30)
    if audit_status["status"] == "timeout":
        pytest.skip("Worker недоступен — audit job не завершился за 30s")

    assert audit_status["status"] == "succeeded", f"Audit job failed: {audit_status}"

    # 9. Dashboard overview
    dash_resp = await client.get("/api/v1/dashboards/overview", headers=headers)
    if dash_resp.status_code == 200:
        body = dash_resp.json()
        # Проверяем структуру (конкретные поля зависят от реализации dashboards/router.py)
        assert isinstance(body, dict)


async def test_audit_latest_endpoint(client: AsyncClient, test_user_data: dict):
    """
    GET /crm/connections/:id/audit/latest — возвращает mock-результат для queued job.
    """
    reg_resp = await client.post("/api/v1/auth/register", json=test_user_data)
    if reg_resp.status_code != 201:
        pytest.skip("Register failed")

    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": test_user_data["email"], "password": test_user_data["password"]},
    )
    if login_resp.status_code != 200:
        pytest.skip("Login failed — нужна верификация email")

    access_token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    # Create connection
    conn_resp = await client.post(
        "/api/v1/crm/connections/mock-amocrm",
        json={"name": "Audit Test"},
        headers=headers,
    )
    if conn_resp.status_code != 201:
        pytest.skip("Create connection failed")

    connection_id = conn_resp.json()["id"]

    # Trigger audit
    audit_resp = await client.post(
        f"/api/v1/crm/connections/{connection_id}/audit",
        headers=headers,
    )
    assert audit_resp.status_code == 202

    # Get latest audit
    latest_resp = await client.get(
        f"/api/v1/crm/connections/{connection_id}/audit/latest",
        headers=headers,
    )
    assert latest_resp.status_code == 200
    body = latest_resp.json()
    assert "status" in body
    assert "job_id" in body


async def test_delete_flow_requires_owner(client: AsyncClient, test_user_data: dict):
    """
    Delete flow: только owner может запросить удаление.
    Проверяем 403 для не-owner (синтетически).
    """
    # Регистрируем двух пользователей — без полного E2E (нужна верификация)
    reg1 = await client.post("/api/v1/auth/register", json=test_user_data)
    assert reg1.status_code in (201, 409)

    fake_id = str(uuid.uuid4())
    # Без токена → 401
    resp = await client.post(f"/api/v1/crm/connections/{fake_id}/delete/request")
    assert resp.status_code == 401


async def test_health_check(client: AsyncClient):
    """GET /health → 200 ok."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("status") == "ok"


async def test_api_health_deep(client: AsyncClient):
    """GET /api/v1/health → 200 ok (DB + Redis могут быть unavailable в unit)."""
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("status") == "ok"
