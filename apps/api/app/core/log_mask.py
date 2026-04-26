"""
Маскировка чувствительных данных в логах.

Правила (docs/security/OAUTH_TOKENS.md §Логирование):
  * `Bearer <token>` → `Bearer ***`;
  * любые значения под ключами `access_token`, `refresh_token`, `authorization`,
    `code_verifier`, `client_secret`, `password`, `code`, `code_hash` → `***`.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

SENSITIVE_KEY_PATTERN = re.compile(
    r"(access_token|refresh_token|authorization|code_verifier|client_secret|"
    r"password|password_hash|code_hash|refresh_token_hash|fernet_key|jwt_secret|"
    r"telegram_bot_token|bot_token)",
    re.IGNORECASE,
)
BEARER_PATTERN = re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]+", re.IGNORECASE)
TELEGRAM_BOT_URL_PATTERN = re.compile(
    r"(api\.telegram\.org/bot)[^/\s]+",
    re.IGNORECASE,
)
DASHBOARD_SHARE_URL_PATTERN = re.compile(
    r"(/dashboard-shares/)[A-Za-z0-9._~\-]+",
    re.IGNORECASE,
)


def mask_string(s: str) -> str:
    """Маскирует Bearer-токены в произвольной строке."""
    masked = BEARER_PATTERN.sub(r"\1***", s)
    masked = TELEGRAM_BOT_URL_PATTERN.sub(r"\1***", masked)
    return DASHBOARD_SHARE_URL_PATTERN.sub(r"\1***", masked)


def mask_value(v: Any) -> Any:
    """Рекурсивно маскирует dict/list. Все значения чувствительных ключей → '***'."""
    if isinstance(v, dict):
        return {
            k: ("***" if SENSITIVE_KEY_PATTERN.search(str(k)) else mask_value(val))
            for k, val in v.items()
        }
    if isinstance(v, (list, tuple)):
        return [mask_value(x) for x in v]
    if isinstance(v, str):
        return mask_string(v)
    text = str(v)
    masked = mask_string(text)
    if masked != text:
        return masked
    return v


def mask_json_like(text: str) -> str:
    """
    Пытается распарсить как JSON и замаскировать — если не получилось, маскирует по regex.
    """
    try:
        data = json.loads(text)
        return json.dumps(mask_value(data), ensure_ascii=False)
    except Exception:
        return mask_string(text)


class MaskingFormatter(logging.Formatter):
    """Log-formatter, который проходит маскировщиком по `msg` и `args`."""

    def format(self, record: logging.LogRecord) -> str:
        try:
            record.msg = mask_string(str(record.msg))
            if isinstance(record.args, dict):
                record.args = mask_value(record.args)
            elif isinstance(record.args, tuple):
                record.args = tuple(mask_value(a) for a in record.args)
        except Exception:
            # Логирование не должно ронять приложение.
            pass
        return super().format(record)


def install_log_masker(level: int = logging.INFO) -> None:
    """
    Ставит маскировщик на root-логгер. Вызывается один раз из main.py.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(
        MaskingFormatter(fmt="%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    for logger_name in ("uvicorn.access", "uvicorn.error"):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.propagate = True
