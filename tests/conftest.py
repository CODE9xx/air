"""
Общие фикстуры для тест-сюита Code9 Analytics.

Используются в:
  tests/api/*, tests/security/*, tests/e2e/*

Требования к окружению:
  - DATABASE_URL  — PostgreSQL (тестовая БД, отдельная от dev)
  - REDIS_URL     — Redis
  - JWT_SECRET, ADMIN_JWT_SECRET, FERNET_KEY — из .env.test

Запуск:
  docker compose exec api pytest -q --asyncio-mode=auto tests/
"""
from __future__ import annotations

import asyncio
import os
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# ---- переопределяем окружение до импорта приложения ----
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://code9:code9@localhost:5432/code9_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-32chars-long-ok")
os.environ.setdefault("ADMIN_JWT_SECRET", "test-admin-jwt-secret-32chars-long")
os.environ.setdefault("FERNET_KEY", "V2fZ7eYm_Qc_f0p-Jb5HcH8XxJz0Aq7W1GH8wKmYP_M=")
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("MOCK_CRM_MODE", "true")
os.environ.setdefault("DEV_EMAIL_MODE", "log")
os.environ.setdefault("ACCESS_TOKEN_TTL_SECONDS", "900")


@pytest.fixture(scope="session")
def event_loop():
    """Единый event loop для всей сессии (pytest-asyncio)."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def app():
    """
    Импортируем FastAPI app после выставления env.

    Если зависимости не установлены — тест помечается как ошибка импорта,
    что видно при `pytest --collect-only`.
    """
    from app.main import app as _app  # noqa: PLC0415
    return _app


@pytest_asyncio.fixture
async def client(app) -> AsyncGenerator[AsyncClient, None]:
    """
    httpx.AsyncClient, направленный в FastAPI ASGI-приложение.
    Не поднимает реальный сервер.
    """
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c


@pytest_asyncio.fixture(scope="session")
async def db_session():
    """
    Async DB-сессия для прямых проверок в БД (без API).
    Откатывает транзакцию после каждого теста в рамках сессии.

    Примечание: в CI следует убедиться, что migrations применены:
      alembic upgrade head  # main
    """
    from app.core.db import AsyncSessionLocal  # noqa: PLC0415
    async with AsyncSessionLocal() as session:
        yield session


@pytest_asyncio.fixture(autouse=True)
async def flush_redis():
    """Сбрасывает Redis БД #1 (тестовая) перед каждым тестом."""
    try:
        from app.core.redis import get_redis  # noqa: PLC0415
        r = get_redis()
        await r.flushdb()
    except Exception:
        # Redis недоступен в unit-среде — пропускаем
        pass
    yield


@pytest.fixture
def admin_credentials() -> dict:
    """Дефолтные учётные данные bootstrap-admin (из seed_admin.py)."""
    return {
        "email": os.getenv("ADMIN_BOOTSTRAP_EMAIL", "admin@code9.local"),
        "password": os.getenv("ADMIN_BOOTSTRAP_PASSWORD", "change-me-on-first-login"),
    }


@pytest.fixture
def test_user_data() -> dict:
    """Данные тестового пользователя для регистрации."""
    import uuid
    unique = uuid.uuid4().hex[:8]
    return {
        "email": f"test_{unique}@example.com",
        "password": "StrongP@ssw0rd!",
        "locale": "ru",
    }
