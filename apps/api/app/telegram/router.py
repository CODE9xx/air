"""Telegram endpoints for the shared CODE9 bot."""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import get_current_user, get_current_workspace
from app.core.redis import get_redis
from app.core.settings import get_settings
from app.db.models import User, Workspace
from app.telegram.client import (
    TelegramChatBinding,
    build_bot_url,
    build_start_parameter,
    find_chat_in_updates,
)

router = APIRouter(prefix="/integrations/telegram", tags=["telegram"])
logger = logging.getLogger("code9.telegram")
CHAT_CACHE_TTL_SECONDS = 60 * 60 * 24 * 30


def _clean_username(username: str) -> str:
    return username.strip().lstrip("@")


def _bot_payload(
    *,
    configured: bool,
    username: str | None,
    verified: bool,
    start_parameter: str | None = None,
) -> dict[str, Any]:
    return {
        "configured": configured,
        "verified": verified,
        "username": username,
        "url": build_bot_url(username, start_parameter),
        "start_parameter": start_parameter,
    }


@router.get("/bot")
async def get_telegram_bot(
    user: User = Depends(get_current_user),
    ws: Workspace = Depends(get_current_workspace),
) -> dict:
    """Return configured shared CODE9 Telegram bot public metadata."""
    del user
    settings = get_settings()
    start_parameter = build_start_parameter(ws.id)
    configured_username = _clean_username(settings.telegram_bot_username)
    if configured_username:
        return _bot_payload(
            configured=bool(settings.telegram_bot_token.strip()),
            username=configured_username,
            verified=False,
            start_parameter=start_parameter,
        )

    token = settings.telegram_bot_token.strip()
    if not token:
        return _bot_payload(
            configured=False,
            username=None,
            verified=False,
            start_parameter=start_parameter,
        )

    try:
        async with httpx.AsyncClient(timeout=settings.telegram_api_timeout_seconds) as client:
            response = await client.get(f"https://api.telegram.org/bot{token}/getMe")
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        logger.warning("telegram_get_me_failed: %s", exc.__class__.__name__)
        return _bot_payload(
            configured=True,
            username=None,
            verified=False,
            start_parameter=start_parameter,
        )

    result = data.get("result") if isinstance(data, dict) else None
    username = _clean_username(str(result.get("username", ""))) if isinstance(result, dict) else ""
    return _bot_payload(
        configured=True,
        username=username or None,
        verified=bool(username),
        start_parameter=start_parameter,
    )


@router.post("/check-chat")
async def check_telegram_chat(
    user: User = Depends(get_current_user),
    ws: Workspace = Depends(get_current_workspace),
) -> dict[str, Any]:
    """Find and cache the Telegram chat that opened the workspace deep-link."""
    del user
    start_parameter = build_start_parameter(ws.id)
    chat = await _find_chat_for_workspace(ws, start_parameter)
    if chat:
        await _cache_chat(ws, chat)
        return {
            "connected": True,
            "start_parameter": start_parameter,
            "chat": chat.to_dict(),
        }

    cached = await _load_cached_chat(ws)
    return {
        "connected": bool(cached),
        "start_parameter": start_parameter,
        "chat": cached.to_dict() if cached else None,
    }


@router.post("/send-test")
async def send_telegram_test(
    user: User = Depends(get_current_user),
    ws: Workspace = Depends(get_current_workspace),
) -> dict[str, Any]:
    """Send a test message to the cached or freshly discovered Telegram chat."""
    del user
    start_parameter = build_start_parameter(ws.id)
    chat = await _load_cached_chat(ws)
    if not chat:
        chat = await _find_chat_for_workspace(ws, start_parameter)
        if chat:
            await _cache_chat(ws, chat)
    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "telegram_chat_not_found",
                    "message": "Open the CODE9 bot and press Start before sending a test message.",
                }
            },
        )

    await _telegram_api_call(
        "sendMessage",
        {
            "chat_id": chat.chat_id,
            "text": f"CODE9 Analytics: тестовое уведомление для проекта «{ws.name}».",
            "disable_web_page_preview": True,
        },
    )
    return {"ok": True, "chat": chat.to_dict()}


async def _find_chat_for_workspace(
    ws: Workspace,
    start_parameter: str,
) -> TelegramChatBinding | None:
    data = await _telegram_api_call(
        "getUpdates",
        {
            "limit": 100,
            "allowed_updates": json.dumps(["message", "edited_message"]),
        },
    )
    result = data.get("result") if isinstance(data, dict) else None
    if not isinstance(result, list):
        logger.warning("telegram_get_updates_unexpected_payload")
        return None
    del ws
    return find_chat_in_updates(result, start_parameter)


async def _telegram_api_call(method: str, payload: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    token = settings.telegram_bot_token.strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": {
                    "code": "telegram_not_configured",
                    "message": "Telegram bot is not configured.",
                }
            },
        )

    try:
        async with httpx.AsyncClient(timeout=settings.telegram_api_timeout_seconds) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{token}/{method}",
                data=payload,
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "telegram_api_http_error: method=%s status=%s",
            method,
            exc.response.status_code,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": {
                    "code": "telegram_api_error",
                    "message": "Telegram API request failed.",
                }
            },
        ) from exc
    except Exception as exc:
        logger.warning("telegram_api_failed: method=%s error=%s", method, exc.__class__.__name__)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": {
                    "code": "telegram_api_error",
                    "message": "Telegram API request failed.",
                }
            },
        ) from exc

    if not isinstance(data, dict) or data.get("ok") is not True:
        logger.warning("telegram_api_not_ok: method=%s", method)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": {
                    "code": "telegram_api_error",
                    "message": "Telegram API request failed.",
                }
            },
        )
    return data


def _chat_cache_key(ws: Workspace) -> str:
    return f"telegram:workspace:{ws.id}:chat"


async def _cache_chat(ws: Workspace, chat: TelegramChatBinding) -> None:
    try:
        redis = get_redis()
        await redis.set(
            _chat_cache_key(ws),
            json.dumps(chat.to_dict()),
            ex=CHAT_CACHE_TTL_SECONDS,
        )
    except Exception as exc:
        logger.warning("telegram_chat_cache_write_failed: %s", exc.__class__.__name__)


async def _load_cached_chat(ws: Workspace) -> TelegramChatBinding | None:
    try:
        redis = get_redis()
        raw = await redis.get(_chat_cache_key(ws))
    except Exception as exc:
        logger.warning("telegram_chat_cache_read_failed: %s", exc.__class__.__name__)
        return None
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return TelegramChatBinding(
            chat_id=int(data["chat_id"]),
            chat_type=str(data.get("chat_type") or "unknown"),
            title=data.get("title"),
            username=data.get("username"),
        )
    except Exception:
        return None
