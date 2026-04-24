"""Internal AIC9 token wallet helpers.

This module deliberately avoids any external payment provider. It only
estimates, reserves, charges, and releases internal service tokens.
"""
from __future__ import annotations

import math
import uuid
from datetime import date
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Job, TokenAccount, TokenLedger, TokenReservation, Workspace

MTOKEN = 1000
EXPORT_REBUILD_TOKENS_PER_CONTACT = 3
PLAN_MONTHLY_TOKENS: dict[str, int] = {
    "free": 0,
    "paygo": 0,
    "start": 3000,
    "team": 9000,
    "pro": 18000,
}


def tokens_to_mtokens(tokens: int | float) -> int:
    return int(math.ceil(float(tokens) * MTOKEN))


def mtokens_to_tokens_floor(mtokens: int) -> int:
    return int(mtokens // MTOKEN)


def mtokens_to_tokens_ceil(mtokens: int) -> int:
    if mtokens <= 0:
        return 0
    return int(math.ceil(mtokens / MTOKEN))


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def _is_all_time(date_from: date, date_to: date) -> bool:
    return date_from <= date(2000, 1, 1) and date_to >= date.today()


def _snapshot_counts(metadata: dict[str, Any]) -> dict[str, Any]:
    snapshot = metadata.get("token_estimate_snapshot")
    if isinstance(snapshot, dict) and isinstance(snapshot.get("counts"), dict):
        return snapshot.get("counts") or {}
    return {}


def _fallback_counts(metadata: dict[str, Any]) -> dict[str, Any]:
    for key in ("active_export",):
        section = metadata.get(key)
        if isinstance(section, dict) and isinstance(section.get("counts"), dict):
            return section.get("counts") or {}
    for key in ("last_pull_counts", "last_trial_export_counts"):
        section = metadata.get(key)
        if isinstance(section, dict):
            return section
    return {}


def build_full_export_quote(
    *,
    connection_id: str,
    date_from: date,
    date_to: date,
    pipeline_ids: list[str],
    metadata: dict[str, Any],
    available_mtokens: int,
    cached_deals_count: int | None,
) -> dict[str, Any]:
    """Estimate the first paid export charge in internal AIC9 tokens.

    Formula for the first version:
    ``estimated unique customers * 3 AIC9 tokens``.

    Full-account snapshots provide the best all-time estimate. For filtered
    periods, a cached deal count scales the full snapshot by deal ratio.
    """
    snapshot = _snapshot_counts(metadata)
    fallback = _fallback_counts(metadata)
    full_deals = _safe_int(snapshot.get("deals"))
    full_contacts = _safe_int(snapshot.get("contacts"))

    basis = "snapshot_scaled"
    estimated_deals = _safe_int(cached_deals_count)
    estimated_contacts = 0

    if snapshot and _is_all_time(date_from, date_to):
        estimated_deals = full_deals
        estimated_contacts = full_contacts
        basis = "full_snapshot"
    elif snapshot and full_deals > 0 and full_contacts > 0 and estimated_deals > 0:
        ratio = min(1.0, estimated_deals / full_deals)
        estimated_contacts = max(1, int(round(full_contacts * ratio)))
        basis = "snapshot_scaled_by_cached_deals"
    elif fallback:
        estimated_deals = estimated_deals or _safe_int(fallback.get("deals"))
        estimated_contacts = _safe_int(fallback.get("contacts"))
        if not estimated_contacts and full_deals > 0 and full_contacts > 0 and estimated_deals:
            estimated_contacts = max(1, int(round(full_contacts * (estimated_deals / full_deals))))
        basis = "cached_counts"
    elif snapshot:
        estimated_deals = full_deals
        estimated_contacts = full_contacts
        basis = "full_snapshot_fallback"

    estimated_tokens = estimated_contacts * EXPORT_REBUILD_TOKENS_PER_CONTACT
    required_mtokens = tokens_to_mtokens(estimated_tokens)
    missing_mtokens = max(0, required_mtokens - max(0, available_mtokens))

    return {
        "connection_id": connection_id,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "pipeline_ids": [str(item) for item in pipeline_ids],
        "pricing_basis": basis,
        "estimated_deals": estimated_deals,
        "estimated_contacts": estimated_contacts,
        "estimated_tokens": mtokens_to_tokens_ceil(required_mtokens),
        "estimated_mtokens": required_mtokens,
        "available_tokens": mtokens_to_tokens_floor(max(0, available_mtokens)),
        "available_mtokens": max(0, available_mtokens),
        "missing_tokens": mtokens_to_tokens_ceil(missing_mtokens),
        "missing_mtokens": missing_mtokens,
        "can_start": missing_mtokens == 0,
        "line_items": [
            {
                "key": "primary_export_customer_history",
                "label": "Первичная AI-подготовка базы",
                "quantity": estimated_contacts,
                "unit_tokens": EXPORT_REBUILD_TOKENS_PER_CONTACT,
                "tokens": mtokens_to_tokens_ceil(required_mtokens),
            }
        ],
    }


async def get_or_create_token_account(
    session: AsyncSession,
    workspace: Workspace,
    *,
    for_update: bool = False,
) -> TokenAccount:
    stmt = select(TokenAccount).where(TokenAccount.workspace_id == workspace.id)
    if for_update:
        stmt = stmt.with_for_update()
    account = (await session.execute(stmt)).scalar_one_or_none()
    if account:
        return account

    account = TokenAccount(
        workspace_id=workspace.id,
        plan_key="free",
        included_monthly_mtokens=0,
        balance_mtokens=0,
        reserved_mtokens=0,
    )
    session.add(account)
    await session.flush()
    return account


def token_account_snapshot(account: TokenAccount) -> dict[str, Any]:
    balance = int(account.balance_mtokens or 0)
    reserved = int(account.reserved_mtokens or 0)
    available = max(0, balance - reserved)
    return {
        "id": str(account.id),
        "workspace_id": str(account.workspace_id),
        "plan_key": account.plan_key,
        "included_monthly_tokens": mtokens_to_tokens_floor(account.included_monthly_mtokens or 0),
        "balance_tokens": mtokens_to_tokens_floor(balance),
        "reserved_tokens": mtokens_to_tokens_ceil(reserved),
        "available_tokens": mtokens_to_tokens_floor(available),
        "balance_mtokens": balance,
        "reserved_mtokens": reserved,
        "available_mtokens": available,
        "created_at": account.created_at.isoformat() if account.created_at else None,
        "updated_at": account.updated_at.isoformat() if account.updated_at else None,
    }


async def reserve_tokens_for_export_job(
    session: AsyncSession,
    *,
    workspace: Workspace,
    crm_connection_id: uuid.UUID,
    job: Job,
    quote: dict[str, Any],
) -> TokenReservation:
    account = await get_or_create_token_account(session, workspace, for_update=True)
    balance = int(account.balance_mtokens or 0)
    reserved = int(account.reserved_mtokens or 0)
    available = max(0, balance - reserved)
    required = int(quote["estimated_mtokens"])
    if required <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": "invalid_token_quote", "message": "Export quote is empty"}},
        )
    if available < required:
        quote = dict(quote)
        quote["available_mtokens"] = available
        quote["available_tokens"] = mtokens_to_tokens_floor(available)
        quote["missing_mtokens"] = required - available
        quote["missing_tokens"] = mtokens_to_tokens_ceil(required - available)
        quote["can_start"] = False
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": {
                    "code": "insufficient_tokens",
                    "message": "Недостаточно AIC9-токенов для выгрузки",
                    "quote": quote,
                }
            },
        )

    account.reserved_mtokens = reserved + required
    reservation = TokenReservation(
        token_account_id=account.id,
        workspace_id=workspace.id,
        crm_connection_id=crm_connection_id,
        job_id=job.id,
        amount_mtokens=required,
        status="reserved",
        reason="full_export",
        description="Резерв токенов: первичная выгрузка amoCRM",
        metadata_json={"quote": quote},
    )
    session.add(reservation)
    await session.flush()
    session.add(
        TokenLedger(
            token_account_id=account.id,
            workspace_id=workspace.id,
            crm_connection_id=crm_connection_id,
            job_id=job.id,
            reservation_id=reservation.id,
            amount_mtokens=0,
            balance_after_mtokens=balance,
            reserved_after_mtokens=account.reserved_mtokens,
            kind="reserve",
            description="Резерв токенов: первичная выгрузка amoCRM",
            reference=f"job:{job.id}",
            metadata_json={"quote": quote},
        )
    )
    return reservation
