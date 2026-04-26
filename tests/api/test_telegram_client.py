from __future__ import annotations

import uuid

from app.telegram.client import build_start_parameter, find_chat_in_updates


def test_build_start_parameter_is_stable_and_safe():
    workspace_id = uuid.UUID("8f3545c4-81c3-48d6-8c30-4e9eebc0c47a")

    assert build_start_parameter(workspace_id) == "code9_8f3545c481c3"


def test_find_chat_in_updates_matches_start_payload():
    start = "code9_8f3545c481c3"
    updates = [
        {"message": {"text": "/start code9_other", "chat": {"id": 1, "type": "private"}}},
        {
            "message": {
                "text": f"/start {start}",
                "chat": {
                    "id": 123456789,
                    "type": "private",
                    "username": "client_chat",
                    "first_name": "Client",
                },
            }
        },
    ]

    chat = find_chat_in_updates(updates, start)

    assert chat is not None
    assert chat.chat_id == 123456789
    assert chat.chat_type == "private"
    assert chat.username == "client_chat"
    assert chat.title == "Client"


def test_find_chat_in_updates_ignores_non_matching_messages():
    updates = [
        {"message": {"text": "hello", "chat": {"id": 1, "type": "private"}}},
        {"message": {"text": "/start code9_other", "chat": {"id": 2, "type": "private"}}},
    ]

    assert find_chat_in_updates(updates, "code9_8f3545c481c3") is None
