"""Billing endpoints — balance, ledger, manual topup (admin-only)."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_admin_role
from app.core.db import get_session
from app.db.models import (
    AdminAuditLog,
    AdminUser,
    BillingAccount,
    BillingLedger,
    CrmConnection,
    User,
    Workspace,
)

router = APIRouter(tags=["billing"])


class ManualTopupRequest(BaseModel):
    amount_cents: int = Field(gt=0)
    reason: str = Field(min_length=1, max_length=500)


async def _load_ws_from_connection(
    session: AsyncSession, connection_id: uuid.UUID, user: User
) -> Workspace:
    row = (
        await session.execute(
            select(CrmConnection, Workspace)
            .join(Workspace, Workspace.id == CrmConnection.workspace_id)
            .where(CrmConnection.id == connection_id)
        )
    ).first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Connection not found"}},
        )
    _, ws = row
    # user access check — через owner_user_id (MVP).
    from app.db.models import WorkspaceMember

    m = (
        await session.execute(
            select(WorkspaceMember)
            .where(WorkspaceMember.workspace_id == ws.id)
            .where(WorkspaceMember.user_id == user.id)
        )
    ).scalar_one_or_none()
    if not m:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "forbidden", "message": "Not a workspace member"}},
        )
    return ws


@router.get("/crm/connections/{connection_id}/billing")
async def get_connection_billing(
    connection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    ws = await _load_ws_from_connection(session, connection_id, user)
    ba = (
        await session.execute(
            select(BillingAccount).where(BillingAccount.workspace_id == ws.id)
        )
    ).scalar_one_or_none()
    if not ba:
        return {"balance_cents": 0, "currency": "RUB", "plan": "free", "ledger": []}

    ledger_rows = (
        await session.execute(
            select(BillingLedger)
            .where(BillingLedger.billing_account_id == ba.id)
            .order_by(BillingLedger.created_at.desc())
            .limit(20)
        )
    ).scalars().all()

    return {
        "balance_cents": ba.balance_cents,
        "currency": ba.currency,
        "plan": ba.plan,
        "provider": ba.provider,
        "ledger": [
            {
                "id": str(r.id),
                "amount_cents": r.amount_cents,
                "currency": r.currency,
                "kind": r.kind,
                "description": r.description,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in ledger_rows
        ],
    }


@router.post("/crm/connections/{connection_id}/billing/manual-topup")
async def manual_topup(
    connection_id: uuid.UUID,
    body: ManualTopupRequest,
    admin: AdminUser = Depends(require_admin_role("superadmin", "support")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    # Находим ws по connection.
    row = (
        await session.execute(
            select(CrmConnection, Workspace)
            .join(Workspace, Workspace.id == CrmConnection.workspace_id)
            .where(CrmConnection.id == connection_id)
        )
    ).first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Connection not found"}},
        )
    _, ws = row

    ba = (
        await session.execute(
            select(BillingAccount).where(BillingAccount.workspace_id == ws.id)
        )
    ).scalar_one_or_none()
    if not ba:
        ba = BillingAccount(workspace_id=ws.id)
        session.add(ba)
        await session.flush()

    ba.balance_cents += body.amount_cents
    ledger = BillingLedger(
        billing_account_id=ba.id,
        workspace_id=ws.id,
        amount_cents=body.amount_cents,
        currency=ba.currency,
        kind="adjustment",
        description=f"Manual topup by admin: {body.reason}",
        reference=f"admin:{admin.id}",
    )
    session.add(ledger)

    # Admin audit log — в той же транзакции.
    audit = AdminAuditLog(
        admin_user_id=admin.id,
        action="billing_adjustment",
        target_type="workspace",
        target_id=ws.id,
        metadata_json={"amount_cents": body.amount_cents, "reason": body.reason},
    )
    session.add(audit)

    await session.commit()
    return {"ok": True, "balance_cents": ba.balance_cents}
