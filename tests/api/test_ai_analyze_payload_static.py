"""Static regression tests for AI job enqueue payloads.

These tests intentionally avoid importing the FastAPI app or touching Redis/DB.
They guard the router-to-worker contract that became visible after RQ enqueue
started passing payloads as ``**kwargs``.
"""
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
AI_ROUTER = ROOT / "apps/api/app/ai/router.py"


def _assigned_dict_in_ai_analyze(name: str) -> dict[str, str]:
    tree = ast.parse(AI_ROUTER.read_text())
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef) or node.name != "ai_analyze":
            continue
        for child in ast.walk(node):
            if not isinstance(child, ast.Assign):
                continue
            if not any(isinstance(t, ast.Name) and t.id == name for t in child.targets):
                continue
            if not isinstance(child.value, ast.Dict):
                raise AssertionError(f"{name} must be assigned a dict literal")
            return {
                ast.literal_eval(k): ast.unparse(v)
                for k, v in zip(child.value.keys, child.value.values, strict=True)
                if k is not None
            }
    raise AssertionError(f"ai_analyze must assign {name}")


def test_ai_analyze_worker_payload_matches_worker_signature() -> None:
    payload = _assigned_dict_in_ai_analyze("worker_payload")

    assert payload.get("workspace_id") == "str(conn.workspace_id)", (
        "worker.jobs.ai.analyze_conversation requires workspace_id as its first "
        "argument; RQ enqueue_call passes worker_payload as kwargs, so the router "
        "must include workspace_id explicitly."
    )
    assert payload.get("connection_id") == "str(conn.id)"


def test_ai_analyze_stored_payload_keeps_mock_marker() -> None:
    payload = _assigned_dict_in_ai_analyze("db_payload")

    assert payload.get("connection_id") == "str(conn.id)"
    assert payload.get("mock") == "True"
