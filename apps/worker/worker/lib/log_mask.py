"""
Маскировщик чувствительных полей в логах worker'а.

Живой маскировщик поддерживает BE (``apps/api/app/core/logging.py``).
Здесь — локальный re-export-совместимый модуль с теми же правилами, чтобы
worker не тянул импорт из api.
"""
from __future__ import annotations

import re
from typing import Any

SENSITIVE_KEYS = frozenset(
    {
        "access_token",
        "refresh_token",
        "authorization",
        "code_verifier",
        "client_secret",
        "password",
        "password_hash",
        "email_code_hash",
        "refresh_token_hash",
        # CR-06 (QA, 2026-04-18): добавлены fernet_key, jwt_secret, admin_jwt_secret —
        # чтобы ключи шифрования не утекали в stdout при случайном логировании.
        # Закрыто Lead Architect как cross-zone minor security fix.
        "fernet_key",
        "jwt_secret",
        "admin_jwt_secret",
    }
)

_BEARER_RE = re.compile(r"Bearer\s+[A-Za-z0-9._\-]+")


def mask_bearer(text: str) -> str:
    """Заменить ``Bearer <token>`` на ``Bearer ***``."""
    return _BEARER_RE.sub("Bearer ***", text)


def mask_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Рекурсивно заменить значения чувствительных ключей на ``***``."""
    out: dict[str, Any] = {}
    for key, value in data.items():
        if key.lower() in SENSITIVE_KEYS:
            out[key] = "***"
        elif isinstance(value, dict):
            out[key] = mask_dict(value)
        elif isinstance(value, list):
            out[key] = [mask_dict(v) if isinstance(v, dict) else v for v in value]
        elif isinstance(value, str):
            out[key] = mask_bearer(value)
        else:
            out[key] = value
    return out
