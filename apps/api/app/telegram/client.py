"""Small Telegram Bot API helpers for the shared CODE9 bot."""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class TelegramChatBinding:
    chat_id: int
    chat_type: str
    title: str | None = None
    username: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_start_parameter(workspace_id: uuid.UUID) -> str:
    """Build a stable Telegram deep-link payload without exposing raw UUIDs."""
    return f"code9_{workspace_id.hex[:12]}"


def build_bot_url(username: str | None, start_parameter: str | None = None) -> str | None:
    if not username:
        return None
    base = f"https://t.me/{username.strip().lstrip('@')}"
    return f"{base}?start={start_parameter}" if start_parameter else base


def find_chat_in_updates(
    updates: list[dict[str, Any]],
    start_parameter: str,
) -> TelegramChatBinding | None:
    """Find the latest chat that sent `/start <workspace-token>` to the bot."""
    for update in reversed(updates):
        message = update.get("message") or update.get("edited_message") or {}
        if not isinstance(message, dict):
            continue

        text = str(message.get("text") or "").strip()
        if not _matches_start_parameter(text, start_parameter):
            continue

        chat = message.get("chat") or {}
        if not isinstance(chat, dict):
            continue

        chat_id = chat.get("id")
        try:
            chat_id_int = int(chat_id)
        except (TypeError, ValueError):
            continue

        return TelegramChatBinding(
            chat_id=chat_id_int,
            chat_type=str(chat.get("type") or "unknown"),
            title=_chat_title(chat),
            username=_clean_optional(chat.get("username")),
        )

    return None


def _matches_start_parameter(text: str, start_parameter: str) -> bool:
    if text == start_parameter:
        return True
    parts = text.split(maxsplit=1)
    if len(parts) != 2:
        return False
    command, payload = parts
    return command.startswith("/start") and payload.strip() == start_parameter


def _chat_title(chat: dict[str, Any]) -> str | None:
    title = _clean_optional(chat.get("title"))
    if title:
        return title
    first_name = _clean_optional(chat.get("first_name"))
    last_name = _clean_optional(chat.get("last_name"))
    full_name = " ".join(part for part in (first_name, last_name) if part)
    return full_name or _clean_optional(chat.get("username"))


def _clean_optional(value: Any) -> str | None:
    cleaned = str(value or "").strip()
    return cleaned or None
