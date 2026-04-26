"""IMAP-first email connections and export jobs."""
from __future__ import annotations

import asyncio
import imaplib
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_workspace_role
from app.core.crypto import decrypt_token, encrypt_token
from app.core.db import get_session
from app.core.jobs import enqueue, queue_for_kind
from app.db.models import CrmConnection, Job, User, WorkspaceMember

router = APIRouter(prefix="/email", tags=["email"])
ws_email_router = APIRouter(tags=["email"])

PROVIDERS = {"gmail", "microsoft", "yandex", "imap"}
SYNC_SCOPES = {"crm_only", "all_mailbox"}
PERIODS = {"last_12_months", "current_year", "all_time"}
_HOST_RE = re.compile(r"^[A-Za-z0-9.-]{1,255}$")


class EmailConnectionCreate(BaseModel):
    provider: str = Field(default="imap")
    email_address: EmailStr
    display_name: str | None = Field(default=None, max_length=160)
    crm_connection_id: uuid.UUID | None = None
    imap_host: str = Field(min_length=3, max_length=255)
    imap_port: int = Field(default=993, ge=1, le=65535)
    imap_ssl: bool = True
    username: str = Field(min_length=1, max_length=255)
    app_password: str = Field(min_length=4, max_length=1024)
    folders: list[str] = Field(default_factory=lambda: ["INBOX"])
    sync_scope: str = "crm_only"
    period: str = "last_12_months"
    test_connection: bool = True


class EmailConnectionPatch(BaseModel):
    display_name: str | None = Field(default=None, max_length=160)
    folders: list[str] | None = None
    sync_scope: str | None = None
    period: str | None = None
    status: str | None = None


class EmailExportRequest(BaseModel):
    folders: list[str] | None = None
    period: str | None = None
    max_messages: int | None = Field(default=None, ge=1, le=250000)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def _clean_folders(value: list[str] | None) -> list[str]:
    items: list[str] = []
    for raw in value or []:
        folder = str(raw or "").strip()
        if any(ch in folder for ch in ("\x00", "\r", "\n")):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"error": {"code": "validation_error", "message": "Bad IMAP folder name"}},
            )
        if folder and folder not in items:
            items.append(folder[:255])
    return items[:20] or ["INBOX"]


def _validate_provider(value: str) -> str:
    provider = (value or "imap").strip().lower()
    if provider not in PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": "validation_error", "message": "Unsupported email provider"}},
        )
    return provider


def _validate_scope(value: str) -> str:
    scope = (value or "crm_only").strip()
    if scope not in SYNC_SCOPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": "validation_error", "message": "Unsupported email sync scope"}},
        )
    return scope


def _validate_period(value: str) -> str:
    period = (value or "last_12_months").strip()
    if period not in PERIODS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": "validation_error", "message": "Unsupported email sync period"}},
        )
    return period


def _validate_host(value: str) -> str:
    host = (value or "").strip()
    if not _HOST_RE.fullmatch(host):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": "validation_error", "message": "Bad IMAP host"}},
        )
    return host


def _imap_test_blocking(
    *,
    host: str,
    port: int,
    use_ssl: bool,
    username: str,
    password: str,
) -> dict[str, Any]:
    client: imaplib.IMAP4 | imaplib.IMAP4_SSL | None = None
    try:
        if use_ssl:
            client = imaplib.IMAP4_SSL(host, port, timeout=20)
        else:
            client = imaplib.IMAP4(host, port, timeout=20)
        typ, _ = client.login(username, password)
        if typ != "OK":
            raise RuntimeError("login_failed")
        typ, boxes = client.list()
        folder_count = len(boxes or []) if typ == "OK" else None
        return {"status": "ok", "folder_count": folder_count}
    except imaplib.IMAP4.error as exc:
        message = str(exc)[:300] or "IMAP auth failed"
        raise RuntimeError(message) from None
    except Exception as exc:
        message = str(exc)[:300] or type(exc).__name__
        raise RuntimeError(message) from None
    finally:
        if client is not None:
            try:
                client.logout()
            except Exception:
                pass


async def _test_imap_settings(
    *,
    host: str,
    port: int,
    use_ssl: bool,
    username: str,
    password: str,
) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(
            _imap_test_blocking,
            host=host,
            port=port,
            use_ssl=use_ssl,
            username=username,
            password=password,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "imap_connection_failed", "message": str(exc)[:300]}},
        ) from None


async def _require_member(
    session: AsyncSession,
    user: User,
    workspace_id: uuid.UUID,
    *,
    write: bool = False,
) -> WorkspaceMember:
    roles = {"owner", "admin"} if write else {"owner", "admin", "analyst", "viewer"}
    return await require_workspace_role(workspace_id, user, session, roles)


async def _resolve_crm_connection(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    crm_connection_id: uuid.UUID | None,
) -> CrmConnection:
    stmt = select(CrmConnection).where(CrmConnection.workspace_id == workspace_id)
    if crm_connection_id:
        stmt = stmt.where(CrmConnection.id == crm_connection_id)
    else:
        stmt = (
            stmt.where(CrmConnection.status == "active")
            .where(CrmConnection.tenant_schema.is_not(None))
            .order_by(CrmConnection.created_at.asc())
            .limit(1)
        )
    conn = (await session.execute(stmt)).scalar_one_or_none()
    if not conn or conn.status in {"deleted", "deleting"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "crm_connection_required",
                    "message": "Connect CRM and create tenant schema before email import",
                }
            },
        )
    if conn.status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "crm_connection_not_active",
                    "message": "CRM connection must be active before email import",
                }
            },
        )
    if not conn.tenant_schema:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "tenant_schema_required",
                    "message": "CRM tenant schema is not ready yet",
                }
            },
        )
    return conn


async def _get_email_connection_for_user(
    session: AsyncSession,
    user: User,
    email_connection_id: uuid.UUID,
    *,
    write: bool = False,
) -> dict[str, Any]:
    row = (
        await session.execute(
            text(
                "SELECT * FROM email_connections "
                "WHERE id = CAST(:id AS UUID) AND deleted_at IS NULL"
            ),
            {"id": str(email_connection_id)},
        )
    ).mappings().first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Email connection not found"}},
        )
    await _require_member(session, user, row["workspace_id"], write=write)
    return dict(row)


def _serialize(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "workspace_id": str(row["workspace_id"]),
        "crm_connection_id": str(row["crm_connection_id"]) if row.get("crm_connection_id") else None,
        "provider": row["provider"],
        "email_address": row["email_address"],
        "display_name": row.get("display_name"),
        "auth_type": row["auth_type"],
        "imap_host": row["imap_host"],
        "imap_port": row["imap_port"],
        "imap_ssl": row["imap_ssl"],
        "username": row["username"],
        "folders": row.get("folders") or [],
        "sync_scope": row["sync_scope"],
        "period": row["period"],
        "status": row["status"],
        "last_sync_at": row["last_sync_at"].isoformat() if row.get("last_sync_at") else None,
        "last_error": row.get("last_error"),
        "last_counts": row.get("last_counts") or {},
        "metadata": row.get("metadata") or {},
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
    }


@ws_email_router.get("/workspaces/{workspace_id}/email/connections")
async def list_workspace_email_connections(
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    await _require_member(session, user, workspace_id)
    rows = (
        await session.execute(
            text(
                "SELECT * FROM email_connections "
                "WHERE workspace_id = CAST(:workspace_id AS UUID) AND deleted_at IS NULL "
                "ORDER BY created_at DESC"
            ),
            {"workspace_id": str(workspace_id)},
        )
    ).mappings().all()
    return [_serialize(dict(row)) for row in rows]


@ws_email_router.post("/workspaces/{workspace_id}/email/connections")
async def create_workspace_email_connection(
    workspace_id: uuid.UUID,
    body: EmailConnectionCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await _require_member(session, user, workspace_id, write=True)
    crm_conn = await _resolve_crm_connection(
        session,
        workspace_id=workspace_id,
        crm_connection_id=body.crm_connection_id,
    )

    provider = _validate_provider(body.provider)
    host = _validate_host(body.imap_host)
    folders = _clean_folders(body.folders)
    sync_scope = _validate_scope(body.sync_scope)
    period = _validate_period(body.period)
    email_address = str(body.email_address).strip().lower()
    username = body.username.strip()

    if body.test_connection:
        await _test_imap_settings(
            host=host,
            port=body.imap_port,
            use_ssl=body.imap_ssl,
            username=username,
            password=body.app_password,
        )

    encrypted_password = encrypt_token(body.app_password)
    row = (
        await session.execute(
            text(
                "INSERT INTO email_connections("
                "  workspace_id, crm_connection_id, created_by_user_id, provider, "
                "  email_address, display_name, imap_host, imap_port, imap_ssl, "
                "  username, password_encrypted, folders, sync_scope, period, "
                "  status, last_error, metadata, updated_at"
                ") VALUES ("
                "  CAST(:workspace_id AS UUID), CAST(:crm_connection_id AS UUID), "
                "  CAST(:user_id AS UUID), :provider, :email_address, :display_name, "
                "  :imap_host, :imap_port, :imap_ssl, :username, :password_encrypted, "
                "  CAST(:folders AS JSONB), :sync_scope, :period, 'active', NULL, "
                "  CAST(:metadata AS JSONB), NOW()"
                ") ON CONFLICT (workspace_id, email_address) DO UPDATE SET "
                "  crm_connection_id = EXCLUDED.crm_connection_id, "
                "  provider = EXCLUDED.provider, "
                "  display_name = EXCLUDED.display_name, "
                "  imap_host = EXCLUDED.imap_host, "
                "  imap_port = EXCLUDED.imap_port, "
                "  imap_ssl = EXCLUDED.imap_ssl, "
                "  username = EXCLUDED.username, "
                "  password_encrypted = EXCLUDED.password_encrypted, "
                "  folders = EXCLUDED.folders, "
                "  sync_scope = EXCLUDED.sync_scope, "
                "  period = EXCLUDED.period, "
                "  status = 'active', "
                "  last_error = NULL, "
                "  deleted_at = NULL, "
                "  metadata = email_connections.metadata || EXCLUDED.metadata, "
                "  updated_at = NOW() "
                "RETURNING *"
            ),
            {
                "workspace_id": str(workspace_id),
                "crm_connection_id": str(crm_conn.id),
                "user_id": str(user.id),
                "provider": provider,
                "email_address": email_address,
                "display_name": body.display_name,
                "imap_host": host,
                "imap_port": body.imap_port,
                "imap_ssl": body.imap_ssl,
                "username": username,
                "password_encrypted": encrypted_password,
                "folders": _json(folders),
                "sync_scope": sync_scope,
                "period": period,
                "metadata": _json({"source": "cabinet_imap", "tenant_schema": crm_conn.tenant_schema}),
            },
        )
    ).mappings().one()
    await session.commit()
    return _serialize(dict(row))


@router.get("/connections/{email_connection_id}")
async def get_email_connection(
    email_connection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    row = await _get_email_connection_for_user(session, user, email_connection_id)
    return _serialize(row)


@router.patch("/connections/{email_connection_id}")
async def patch_email_connection(
    email_connection_id: uuid.UUID,
    body: EmailConnectionPatch,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    row = await _get_email_connection_for_user(session, user, email_connection_id, write=True)
    folders = _clean_folders(body.folders) if body.folders is not None else row.get("folders") or ["INBOX"]
    sync_scope = _validate_scope(body.sync_scope or row["sync_scope"])
    period = _validate_period(body.period or row["period"])
    new_status = body.status or row["status"]
    if new_status not in {"active", "paused"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": "validation_error", "message": "Unsupported email connection status"}},
        )
    updated = (
        await session.execute(
            text(
                "UPDATE email_connections SET "
                "  display_name = COALESCE(:display_name, display_name), "
                "  folders = CAST(:folders AS JSONB), "
                "  sync_scope = :sync_scope, "
                "  period = :period, "
                "  status = :status, "
                "  updated_at = NOW() "
                "WHERE id = CAST(:id AS UUID) "
                "RETURNING *"
            ),
            {
                "id": str(email_connection_id),
                "display_name": body.display_name,
                "folders": _json(folders),
                "sync_scope": sync_scope,
                "period": period,
                "status": new_status,
            },
        )
    ).mappings().one()
    await session.commit()
    return _serialize(dict(updated))


@router.post("/connections/{email_connection_id}/test")
async def test_email_connection(
    email_connection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    row = await _get_email_connection_for_user(session, user, email_connection_id)
    password = decrypt_token(row["password_encrypted"])
    result = await _test_imap_settings(
        host=row["imap_host"],
        port=int(row["imap_port"]),
        use_ssl=bool(row["imap_ssl"]),
        username=row["username"],
        password=password,
    )
    await session.execute(
        text(
            "UPDATE email_connections SET status='active', last_error=NULL, updated_at=NOW() "
            "WHERE id = CAST(:id AS UUID)"
        ),
        {"id": str(email_connection_id)},
    )
    await session.commit()
    return result


@router.post("/connections/{email_connection_id}/export")
async def export_email_connection(
    email_connection_id: uuid.UUID,
    body: EmailExportRequest | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    row = await _get_email_connection_for_user(session, user, email_connection_id, write=True)
    if row["status"] not in {"active", "error"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "bad_status", "message": "Email connection is not active"}},
        )
    crm_conn = await _resolve_crm_connection(
        session,
        workspace_id=row["workspace_id"],
        crm_connection_id=row["crm_connection_id"],
    )
    request = body or EmailExportRequest()
    folders = _clean_folders(request.folders) if request.folders else row.get("folders") or ["INBOX"]
    period = _validate_period(request.period or row["period"])
    payload = {
        "email_connection_id": str(email_connection_id),
        "folders": folders,
        "period": period,
        "max_messages": request.max_messages,
    }
    job = Job(
        workspace_id=row["workspace_id"],
        crm_connection_id=crm_conn.id,
        kind="pull_email_imap",
        queue=queue_for_kind("pull_email_imap"),
        status="queued",
        payload=payload,
    )
    session.add(job)
    await session.flush()
    rq_id = enqueue("pull_email_imap", payload, job_row_id=str(job.id))
    job.rq_job_id = rq_id
    await session.commit()
    return {"job_id": str(job.id), "rq_job_id": rq_id}
