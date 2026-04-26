"""IMAP email import jobs.

Imports email metadata and cleaned text into the CRM tenant schema. Secrets stay
in public.email_connections.password_encrypted and never enter job payloads.
"""
from __future__ import annotations

import email
import hashlib
import imaplib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from email import policy
from email.header import decode_header, make_header
from email.utils import getaddresses, parsedate_to_datetime
from typing import Any

from sqlalchemy import text

from ..lib.crypto import decrypt_token
from ..lib.db import sync_session
from ._common import (
    create_job_notification,
    mark_job_failed,
    mark_job_running,
    mark_job_succeeded,
    update_job_progress,
)

_TENANT_SCHEMA_RE = re.compile(r"^crm_amo_[0-9a-f]{8}$")
_TAGS_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")
_MAX_BODY_CHARS = 100_000


def _json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def _pii_salt() -> str:
    return os.getenv("PII_HASH_SALT", "code9-pii-v1")


def _normalize_email(raw: str | None) -> str | None:
    if not raw:
        return None
    value = raw.strip().lower()
    return value or None


def _hash_email(raw: str | None) -> str | None:
    value = _normalize_email(raw)
    if not value:
        return None
    return hashlib.sha256((_pii_salt() + value).encode("utf-8")).hexdigest()


def _safe_error(exc: Exception) -> str:
    message = str(exc) or type(exc).__name__
    return message.replace("\n", " ")[:1000]


def _fetch_connection(email_connection_id: str) -> dict[str, Any]:
    with sync_session() as sess:
        row = sess.execute(
            text(
                "SELECT ec.id, ec.workspace_id, ec.crm_connection_id, ec.provider, "
                "       ec.email_address, ec.imap_host, ec.imap_port, ec.imap_ssl, "
                "       ec.username, ec.password_encrypted, ec.folders, ec.period, "
                "       ec.sync_scope, ec.status, c.tenant_schema "
                "FROM email_connections ec "
                "JOIN crm_connections c ON c.id = ec.crm_connection_id "
                "WHERE ec.id = CAST(:id AS UUID) "
                "  AND ec.deleted_at IS NULL "
                "  AND c.deleted_at IS NULL"
            ),
            {"id": email_connection_id},
        ).mappings().first()
        if row is None:
            raise RuntimeError("email connection not found")
        data = dict(row)
    if data["status"] not in {"active", "error"}:
        raise RuntimeError("email connection is not active")
    schema = str(data.get("tenant_schema") or "")
    if not _TENANT_SCHEMA_RE.fullmatch(schema):
        raise RuntimeError("tenant schema is not ready")
    return data


def _connect_imap(conn: dict[str, Any]) -> imaplib.IMAP4 | imaplib.IMAP4_SSL:
    password = decrypt_token(conn["password_encrypted"])
    host = str(conn["imap_host"])
    port = int(conn["imap_port"])
    use_ssl = bool(conn["imap_ssl"])
    if use_ssl:
        client: imaplib.IMAP4 | imaplib.IMAP4_SSL = imaplib.IMAP4_SSL(host, port, timeout=30)
    else:
        client = imaplib.IMAP4(host, port, timeout=30)
    typ, _ = client.login(str(conn["username"]), password)
    if typ != "OK":
        raise RuntimeError("IMAP login failed")
    return client


def _period_to_since(period: str) -> datetime | None:
    now = datetime.now(timezone.utc)
    if period == "last_12_months":
        return now - timedelta(days=365)
    if period == "current_year":
        return datetime(now.year, 1, 1, tzinfo=timezone.utc)
    return None


def _imap_date(dt: datetime) -> str:
    return dt.strftime("%d-%b-%Y")


def _decode_header_value(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(make_header(decode_header(value))).strip() or None
    except Exception:
        return value.strip()[:1000] or None


def _message_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
    except Exception:
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _clean_html(value: str) -> str:
    value = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", value)
    value = _TAGS_RE.sub(" ", value)
    return _SPACE_RE.sub(" ", value).strip()


def _extract_body(msg: email.message.EmailMessage) -> str | None:
    try:
        part = msg.get_body(preferencelist=("plain", "html"))
    except Exception:
        part = None
    text_value: str | None = None
    if part is not None:
        try:
            text_value = part.get_content()
        except Exception:
            text_value = None
        if text_value and part.get_content_type() == "text/html":
            text_value = _clean_html(text_value)
    if not text_value and msg.is_multipart():
        chunks: list[str] = []
        for part in msg.walk():
            if part.get_content_disposition() == "attachment":
                continue
            if part.get_content_type() not in {"text/plain", "text/html"}:
                continue
            try:
                chunk = part.get_content()
            except Exception:
                continue
            if part.get_content_type() == "text/html":
                chunk = _clean_html(chunk)
            if chunk:
                chunks.append(chunk)
        text_value = "\n\n".join(chunks)
    if not text_value and not msg.is_multipart():
        try:
            text_value = msg.get_content()
        except Exception:
            text_value = None
    if not text_value:
        return None
    text_value = text_value.replace("\x00", " ")
    text_value = _SPACE_RE.sub(" ", text_value).strip()
    return text_value[:_MAX_BODY_CHARS] or None


def _addresses(header_value: str | None) -> list[tuple[str, str]]:
    decoded = _decode_header_value(header_value)
    return [(name, addr) for name, addr in getaddresses([decoded or ""]) if addr]


def _parse_message(raw: bytes, *, folder: str, uid: str) -> dict[str, Any]:
    msg = email.message_from_bytes(raw, policy=policy.default)
    subject = _decode_header_value(msg.get("subject"))
    from_addresses = _addresses(msg.get("from"))
    to_addresses = _addresses(msg.get("to"))
    cc_addresses = _addresses(msg.get("cc"))
    from_name = from_addresses[0][0] if from_addresses else None
    from_hash = _hash_email(from_addresses[0][1]) if from_addresses else None
    to_hashes = sorted({h for _, addr in to_addresses if (h := _hash_email(addr))})
    cc_hashes = sorted({h for _, addr in cc_addresses if (h := _hash_email(addr))})
    participant_hashes = sorted({h for h in [from_hash, *to_hashes, *cc_hashes] if h})
    body = _extract_body(msg)
    attachments_count = 0
    try:
        attachments_count = sum(1 for _ in msg.iter_attachments())
    except Exception:
        attachments_count = 0
    sent_at = _message_datetime(msg.get("date"))
    message_id = (msg.get("message-id") or "").strip() or None
    return {
        "external_id": f"{folder}:{uid}",
        "folder": folder,
        "uid": uid,
        "message_id": message_id[:500] if message_id else None,
        "subject": subject[:2000] if subject else None,
        "body_text": body,
        "body_preview": body[:500] if body else None,
        "from_name": from_name[:500] if from_name else None,
        "from_email_hash": from_hash,
        "to_email_hashes": to_hashes,
        "cc_email_hashes": cc_hashes,
        "participant_hashes": participant_hashes,
        "sent_at": sent_at,
        "received_at": sent_at,
        "size_bytes": len(raw),
        "has_attachments": attachments_count > 0,
        "attachments_count": attachments_count,
        "raw_metadata": {
            "content_type": msg.get_content_type(),
            "in_reply_to": (msg.get("in-reply-to") or "")[:500] or None,
            "references_present": bool(msg.get("references")),
        },
    }


def _insert_message(sess, *, schema: str, email_connection_id: str, item: dict[str, Any]) -> None:
    sess.execute(text(f'SET LOCAL search_path = "{schema}", public'))
    sess.execute(
        text(
            "INSERT INTO email_messages("
            "  email_connection_id, external_id, folder, uid, message_id, subject, "
            "  body_text, body_preview, from_name, from_email_hash, to_email_hashes, "
            "  cc_email_hashes, participant_hashes, sent_at, received_at, size_bytes, "
            "  has_attachments, attachments_count, raw_metadata, fetched_at"
            ") VALUES ("
            "  CAST(:email_connection_id AS UUID), :external_id, :folder, :uid, "
            "  :message_id, :subject, :body_text, :body_preview, :from_name, "
            "  :from_email_hash, CAST(:to_email_hashes AS JSONB), "
            "  CAST(:cc_email_hashes AS JSONB), CAST(:participant_hashes AS JSONB), "
            "  :sent_at, :received_at, :size_bytes, :has_attachments, "
            "  :attachments_count, CAST(:raw_metadata AS JSONB), NOW()"
            ") ON CONFLICT (email_connection_id, external_id) DO UPDATE SET "
            "  message_id = EXCLUDED.message_id, "
            "  subject = EXCLUDED.subject, "
            "  body_text = EXCLUDED.body_text, "
            "  body_preview = EXCLUDED.body_preview, "
            "  from_name = EXCLUDED.from_name, "
            "  from_email_hash = EXCLUDED.from_email_hash, "
            "  to_email_hashes = EXCLUDED.to_email_hashes, "
            "  cc_email_hashes = EXCLUDED.cc_email_hashes, "
            "  participant_hashes = EXCLUDED.participant_hashes, "
            "  sent_at = EXCLUDED.sent_at, "
            "  received_at = EXCLUDED.received_at, "
            "  size_bytes = EXCLUDED.size_bytes, "
            "  has_attachments = EXCLUDED.has_attachments, "
            "  attachments_count = EXCLUDED.attachments_count, "
            "  raw_metadata = EXCLUDED.raw_metadata, "
            "  fetched_at = NOW()"
        ),
        {
            "email_connection_id": email_connection_id,
            "external_id": item["external_id"],
            "folder": item["folder"],
            "uid": item["uid"],
            "message_id": item["message_id"],
            "subject": item["subject"],
            "body_text": item["body_text"],
            "body_preview": item["body_preview"],
            "from_name": item["from_name"],
            "from_email_hash": item["from_email_hash"],
            "to_email_hashes": _json(item["to_email_hashes"]),
            "cc_email_hashes": _json(item["cc_email_hashes"]),
            "participant_hashes": _json(item["participant_hashes"]),
            "sent_at": item["sent_at"],
            "received_at": item["received_at"],
            "size_bytes": item["size_bytes"],
            "has_attachments": item["has_attachments"],
            "attachments_count": item["attachments_count"],
            "raw_metadata": _json(item["raw_metadata"]),
        },
    )


def _load_crm_email_hashes(schema: str) -> set[str]:
    with sync_session() as sess:
        sess.execute(text(f'SET LOCAL search_path = "{schema}", public'))
        rows = sess.execute(
            text(
                "SELECT email_primary_hash AS h FROM contacts WHERE email_primary_hash IS NOT NULL "
                "UNION "
                "SELECT email_hash AS h FROM crm_users WHERE email_hash IS NOT NULL"
            )
        ).scalars().all()
    return {str(row) for row in rows if row}


def _update_email_connection_status(
    email_connection_id: str,
    *,
    status: str,
    counts: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    with sync_session() as sess:
        sess.execute(
            text(
                "UPDATE email_connections SET "
                "  status = :status, "
                "  last_sync_at = CASE WHEN :status = 'active' THEN NOW() ELSE last_sync_at END, "
                "  last_error = :error, "
                "  last_counts = CASE WHEN :counts IS NULL THEN last_counts ELSE CAST(:counts AS JSONB) END, "
                "  updated_at = NOW() "
                "WHERE id = CAST(:id AS UUID)"
            ),
            {
                "id": email_connection_id,
                "status": status,
                "error": error,
                "counts": _json(counts) if counts is not None else None,
            },
        )


def _folder_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return ["INBOX"]


def pull_email_imap(
    email_connection_id: str,
    *,
    folders: list[str] | None = None,
    period: str | None = None,
    max_messages: int | None = None,
    job_row_id: str | None = None,
) -> dict[str, Any]:
    """Pull email messages from IMAP into the linked CRM tenant schema."""
    mark_job_running(job_row_id)
    client: imaplib.IMAP4 | imaplib.IMAP4_SSL | None = None
    counts: dict[str, Any] = {
        "folders": 0,
        "messages_seen": 0,
        "messages_imported": 0,
        "messages_skipped": 0,
        "messages_failed": 0,
        "bytes_seen": 0,
    }
    try:
        conn = _fetch_connection(email_connection_id)
        schema = str(conn["tenant_schema"])
        selected_folders = folders or _folder_list(conn.get("folders"))
        selected_period = period or str(conn.get("period") or "last_12_months")
        sync_scope = str(conn.get("sync_scope") or "crm_only")
        crm_email_hashes = _load_crm_email_hashes(schema) if sync_scope == "crm_only" else set()
        since = _period_to_since(selected_period)
        client = _connect_imap(conn)

        total_steps = max(1, len(selected_folders))
        for folder_index, folder in enumerate(selected_folders, start=1):
            folder = str(folder).strip()
            if not folder:
                continue
            update_job_progress(
                job_row_id,
                stage=f"folder:{folder}",
                completed_steps=folder_index - 1,
                total_steps=total_steps,
                counts=counts,
            )
            typ, _ = client.select(f'"{folder}"', readonly=True)
            if typ != "OK":
                counts["messages_failed"] += 1
                continue
            counts["folders"] += 1
            if since is not None:
                typ, data = client.uid("search", None, "SINCE", _imap_date(since))
            else:
                typ, data = client.uid("search", None, "ALL")
            if typ != "OK" or not data:
                continue
            uids = [uid for uid in data[0].split() if uid]
            if max_messages:
                remaining = max(0, int(max_messages) - int(counts["messages_seen"]))
                uids = uids[-remaining:] if remaining else []
            for uid_raw in uids:
                uid = uid_raw.decode("ascii", "ignore")
                if not uid:
                    continue
                counts["messages_seen"] += 1
                try:
                    typ, msg_data = client.uid("fetch", uid_raw, "(RFC822)")
                    if typ != "OK" or not msg_data:
                        counts["messages_failed"] += 1
                        continue
                    raw_bytes = b""
                    for part in msg_data:
                        if isinstance(part, tuple) and isinstance(part[1], bytes):
                            raw_bytes += part[1]
                    if not raw_bytes:
                        counts["messages_failed"] += 1
                        continue
                    counts["bytes_seen"] += len(raw_bytes)
                    parsed = _parse_message(raw_bytes, folder=folder, uid=uid)
                    if sync_scope == "crm_only":
                        participant_hashes = set(parsed.get("participant_hashes") or [])
                        if not participant_hashes.intersection(crm_email_hashes):
                            counts["messages_skipped"] += 1
                            continue
                    with sync_session() as sess:
                        _insert_message(
                            sess,
                            schema=schema,
                            email_connection_id=email_connection_id,
                            item=parsed,
                        )
                    counts["messages_imported"] += 1
                except Exception:
                    counts["messages_failed"] += 1
                if max_messages and int(counts["messages_seen"]) >= int(max_messages):
                    break
            if max_messages and int(counts["messages_seen"]) >= int(max_messages):
                break

        result = {
            "email_connection_id": email_connection_id,
            "tenant_schema": schema,
            "period": selected_period,
            "sync_scope": sync_scope,
            "folders": selected_folders,
            "counts": counts,
        }
        _update_email_connection_status(email_connection_id, status="active", counts=counts)
        mark_job_succeeded(job_row_id, result)
        create_job_notification(
            job_row_id,
            kind="sync_complete",
            title="Выгрузка почты завершена",
            body=f"Импортировано писем: {counts['messages_imported']}",
            metadata={"email_connection_id": email_connection_id, "counts": counts},
        )
        return result
    except Exception as exc:
        err = _safe_error(exc)
        _update_email_connection_status(email_connection_id, status="error", error=err)
        mark_job_failed(job_row_id, f"pull_email_imap: {err}")
        create_job_notification(
            job_row_id,
            kind="sync_failed",
            title="Выгрузка почты не завершилась",
            body=err,
            metadata={"email_connection_id": email_connection_id},
        )
        raise
    finally:
        if client is not None:
            try:
                client.logout()
            except Exception:
                pass
