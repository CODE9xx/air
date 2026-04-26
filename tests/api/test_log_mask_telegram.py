from __future__ import annotations

import logging
from io import StringIO

import httpx

from app.core.log_mask import MaskingFormatter, mask_string


def test_mask_string_hides_telegram_bot_token_in_api_url():
    masked = mask_string(
        "POST https://api.telegram.org/bot123456:ABC_SECRET/getUpdates HTTP/1.1"
    )

    assert "ABC_SECRET" not in masked
    assert "bot123456:" not in masked
    assert "api.telegram.org/bot***" in masked


def test_mask_string_hides_dashboard_share_token_in_api_url():
    masked = mask_string(
        "GET /api/v1/dashboard-shares/abcDEF_123-secret-token HTTP/1.1"
    )

    assert "abcDEF_123-secret-token" not in masked
    assert "/dashboard-shares/***" in masked


def test_masking_formatter_hides_httpx_url_argument():
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(MaskingFormatter("%(message)s"))
    logger = logging.getLogger("code9-test-log-mask-telegram")
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    logger.info(
        "HTTP Request: %s",
        httpx.URL("https://api.telegram.org/bot123456:ABC_SECRET/getUpdates"),
    )

    output = stream.getvalue()
    assert "ABC_SECRET" not in output
    assert "bot123456:" not in output
    assert "api.telegram.org/bot***" in output
