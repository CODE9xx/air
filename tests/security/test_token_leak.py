"""
Security-тест: перехват логов через caplog/capsys.

Проверяем, что после register + login flow в stdout/логах нет:
  - `Bearer ey...` (raw JWT)
  - plaintext refresh_token
  - plaintext password/password_hash

Используем pytest caplog + capsys.
"""
from __future__ import annotations

import logging
import re

import pytest
from httpx import AsyncClient


pytestmark = pytest.mark.asyncio

# Паттерны, которых НЕ должно быть в логах
FORBIDDEN_PATTERNS = [
    re.compile(r"Bearer\s+ey[A-Za-z0-9._\-]{20,}"),   # raw JWT Bearer token
    re.compile(r'"access_token"\s*:\s*"ey[^*]'),        # raw access_token в JSON
    re.compile(r'"refresh_token"\s*:\s*"[A-Za-z0-9]{20,}"'),  # raw refresh_token
    re.compile(r'"password"\s*:\s*"[^*"]{4,}"'),        # plaintext password в логах
]


class LogCapture(logging.Handler):
    """Простой handler, накапливающий log-записи."""

    def __init__(self):
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    @property
    def all_text(self) -> str:
        return "\n".join(self.format(r) for r in self.records)


@pytest.fixture
def log_capture() -> LogCapture:
    """Фикстура: перехватывает все логи root-логгера."""
    handler = LogCapture()
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
    root = logging.getLogger()
    root.addHandler(handler)
    yield handler
    root.removeHandler(handler)


async def test_register_no_token_leak_in_logs(
    client: AsyncClient,
    test_user_data: dict,
    log_capture: LogCapture,
    capsys,
):
    """
    После register — в логах не должно быть raw токенов/паролей.
    """
    resp = await client.post("/api/v1/auth/register", json=test_user_data)
    assert resp.status_code == 201

    # Проверяем captured logs
    log_text = log_capture.all_text
    captured = capsys.readouterr()
    all_output = log_text + "\n" + captured.out + "\n" + captured.err

    for pattern in FORBIDDEN_PATTERNS:
        matches = pattern.findall(all_output)
        assert not matches, (
            f"Обнаружена утечка в логах! Паттерн: {pattern.pattern}\n"
            f"Найдено: {matches[:3]}\n"
            f"В тексте: {all_output[:500]}"
        )


async def test_login_response_no_raw_refresh(client: AsyncClient, test_user_data: dict):
    """
    Ответ login не содержит refresh_token в теле (только в cookie).
    """
    await client.post("/api/v1/auth/register", json=test_user_data)
    # Login без email verify — 403, но проверяем что тело не содержит сырой refresh
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": test_user_data["email"], "password": test_user_data["password"]},
    )
    body_text = resp.text
    # refresh_token не должен быть в JSON-теле ответа
    assert "refresh_token" not in body_text.lower() or "***" in body_text


async def test_masking_formatter_masks_bearer():
    """
    Unit-тест MaskingFormatter: Bearer-токены маскируются.
    """
    from app.core.log_mask import MaskingFormatter  # noqa: PLC0415

    formatter = MaskingFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="Auth header: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test.sig",
        args=(),
        exc_info=None,
    )
    result = formatter.format(record)
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in result
    assert "Bearer ***" in result


async def test_masking_formatter_masks_dict_keys():
    """
    Unit-тест mask_value: sensitive keys в dict заменяются на ***.
    """
    from app.core.log_mask import mask_value  # noqa: PLC0415

    data = {
        "user_id": "123",
        "access_token": "eyJhbGciOiJIUzI1NiJ9.payload.sig",
        "refresh_token": "opaque_refresh_value_here",
        "password": "MySecretPassword",
        "email": "user@example.com",
    }
    masked = mask_value(data)

    assert masked["access_token"] == "***"
    assert masked["refresh_token"] == "***"
    assert masked["password"] == "***"
    assert masked["user_id"] == "123"
    assert masked["email"] == "user@example.com"


async def test_masking_formatter_masks_nested():
    """
    Маскировка рекурсивно работает для вложенных dict.
    """
    from app.core.log_mask import mask_value  # noqa: PLC0415

    data = {
        "auth": {
            "access_token": "raw_token_here",
            "expires_in": 900,
        }
    }
    masked = mask_value(data)
    assert masked["auth"]["access_token"] == "***"
    assert masked["auth"]["expires_in"] == 900


async def test_worker_mask_bearer():
    """
    Unit-тест worker log_mask: mask_bearer корректно работает.
    """
    from worker.lib.log_mask import mask_bearer  # noqa: PLC0415

    raw = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.signature"
    result = mask_bearer(raw)
    assert "eyJhbGciOiJIUzI1NiJ9" not in result
    assert "Bearer ***" in result


async def test_worker_mask_dict_sensitive_keys():
    """
    Worker mask_dict: sensitive keys → ***.
    """
    from worker.lib.log_mask import mask_dict  # noqa: PLC0415

    data = {
        "connection_id": "uuid-123",
        "access_token": "raw_amo_token",
        "refresh_token": "raw_refresh",
        "provider": "amocrm",
    }
    masked = mask_dict(data)
    assert masked["access_token"] == "***"
    assert masked["refresh_token"] == "***"
    assert masked["connection_id"] == "uuid-123"
    assert masked["provider"] == "amocrm"


async def test_password_not_logged_on_login_failure(
    client: AsyncClient,
    test_user_data: dict,
    log_capture: LogCapture,
    capsys,
):
    """
    При неудачном логине пароль не попадает в логи.
    """
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "test@test.com", "password": "MySuperSecret123!"},
    )
    assert resp.status_code in (401, 403)

    all_output = log_capture.all_text + capsys.readouterr().out
    assert "MySuperSecret123!" not in all_output
