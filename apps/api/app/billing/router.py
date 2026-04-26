"""Billing endpoints — balance, ledger, manual topup (admin-only)."""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_admin_role
from app.billing.tokens import (
    credit_tokens,
    get_or_create_token_account,
    mtokens_to_tokens_ceil,
    token_account_snapshot,
    tokens_to_mtokens,
)
from app.core.db import get_session
from app.core.settings import get_settings
from app.db.models import (
    AdminAuditLog,
    AdminUser,
    BillingAccount,
    BillingLedger,
    CrmConnection,
    PaymentOrder,
    TokenLedger,
    User,
    Workspace,
    WorkspaceMember,
)

router = APIRouter(tags=["billing"])
settings = get_settings()

PLAN_CATALOG: dict[str, dict[str, Any]] = {
    "start": {
        "name": "Старт",
        "tokens": 3000,
        "prices": {"monthly": 4990, "six": 26900, "year": 47900},
    },
    "team": {
        "name": "Команда",
        "tokens": 9000,
        "prices": {"monthly": 9990, "six": 53900, "year": 95900},
    },
    "pro": {
        "name": "Про",
        "tokens": 18000,
        "prices": {"monthly": 14990, "six": 80900, "year": 143900},
    },
    "enterprise": {
        "name": "Enterprise",
        "tokens": 50000,
        "prices": {"monthly": 39990, "six": 215900, "year": 383900},
    },
}
PERIOD_MONTHS = {"monthly": 1, "six": 6, "year": 12}
TOKEN_PACK_CATALOG: dict[str, dict[str, Any]] = {
    "call3000": {"name": "Call Pack 3 000", "tokens": 3000, "price": 2990},
    "u3000": {"name": "Universal 3 000", "tokens": 3000, "price": 2990},
    "u10000": {"name": "Universal 10 000", "tokens": 10000, "price": 8490},
    "u25000": {"name": "Universal 25 000", "tokens": 25000, "price": 19990},
    "tokens_10000": {"name": "10 000 AIC9 tokens", "tokens": 10000, "price": 3000},
    "tokens_25000": {"name": "25 000 AIC9 tokens", "tokens": 25000, "price": 7000},
    "tokens_50000": {"name": "50 000 AIC9 tokens", "tokens": 50000, "price": 12000},
}
SUBSCRIPTION_MODULE_CATALOG: dict[str, dict[str, Any]] = {
    "knowledge_bot": {"name": "Чат-боты на базе знаний", "price": 5000},
    "ai_rop": {"name": "РОП — контроль упущенных сделок", "price": 5000},
    "auto_actions": {"name": "Автодействия системы", "price": 3000},
    "speech_analytics": {"name": "Речевая аналитика", "price": 7000},
}
SLA_CATALOG: dict[str, dict[str, Any]] = {
    "priority_queue": {"name": "Приоритетная очередь", "price": 10000},
    "sla": {"name": "SLA", "price": 20000},
}


class ManualTopupRequest(BaseModel):
    amount_cents: int = Field(gt=0)
    reason: str = Field(min_length=1, max_length=500)


class PayerCompany(BaseModel):
    inn: str = Field(min_length=5, max_length=20)
    kpp: str | None = Field(default=None, max_length=20)
    name: str = Field(min_length=1, max_length=500)
    ogrn: str | None = Field(default=None, max_length=32)
    address: str | None = Field(default=None, max_length=1000)


class PartySuggestRequest(BaseModel):
    query: str = Field(min_length=3, max_length=200)
    count: int = Field(default=5, ge=1, le=10)


class PaymentCreateRequest(BaseModel):
    purchase_type: str = Field(pattern="^(token_topup|subscription)$")
    token_pack_key: str | None = Field(default=None, max_length=64)
    plan_key: str | None = Field(default=None, max_length=64)
    period: str = Field(default="monthly", pattern="^(monthly|six|year)$")
    addon_keys: list[str] = Field(default_factory=list, max_length=10)
    sla_keys: list[str] = Field(default_factory=list, max_length=10)
    payer: PayerCompany | None = None


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


async def _load_ws(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    user: User,
) -> Workspace:
    ws = (
        await session.execute(select(Workspace).where(Workspace.id == workspace_id))
    ).scalar_one_or_none()
    if not ws:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Workspace not found"}},
        )
    member = (
        await session.execute(
            select(WorkspaceMember)
            .where(WorkspaceMember.workspace_id == workspace_id)
            .where(WorkspaceMember.user_id == user.id)
        )
    ).scalar_one_or_none()
    if not member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "forbidden", "message": "Not a workspace member"}},
        )
    return ws


def _serialize_token_ledger(row: TokenLedger) -> dict[str, Any]:
    amount = int(row.amount_mtokens or 0)
    return {
        "id": str(row.id),
        "kind": row.kind,
        "amount_tokens": (
            -mtokens_to_tokens_ceil(abs(amount)) if amount < 0 else mtokens_to_tokens_ceil(amount)
        ),
        "amount_mtokens": amount,
        "balance_after_tokens": mtokens_to_tokens_ceil(row.balance_after_mtokens or 0),
        "reserved_after_tokens": mtokens_to_tokens_ceil(row.reserved_after_mtokens or 0),
        "description": row.description,
        "reference": row.reference,
        "crm_connection_id": str(row.crm_connection_id) if row.crm_connection_id else None,
        "job_id": str(row.job_id) if row.job_id else None,
        "reservation_id": str(row.reservation_id) if row.reservation_id else None,
        "metadata": row.metadata_json or {},
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _serialize_billing_account(ba: BillingAccount | None) -> dict[str, Any]:
    if not ba:
        return {"balance_cents": 0, "currency": "RUB", "plan": "free", "provider": "manual"}
    return {
        "balance_cents": int(ba.balance_cents or 0),
        "currency": ba.currency,
        "plan": ba.plan,
        "provider": ba.provider,
    }


def _serialize_billing_ledger(row: BillingLedger) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "amount_cents": int(row.amount_cents or 0),
        "currency": row.currency,
        "kind": row.kind,
        "description": row.description,
        "reference": row.reference,
        "metadata": row.metadata_json or {},
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _serialize_payment_order(order: PaymentOrder) -> dict[str, Any]:
    return {
        "id": str(order.id),
        "workspace_id": str(order.workspace_id),
        "provider": order.provider,
        "method": order.method,
        "purpose": order.purpose,
        "status": order.status,
        "amount_cents": int(order.amount_cents or 0),
        "currency": order.currency,
        "token_amount_tokens": mtokens_to_tokens_ceil(order.token_amount_mtokens or 0),
        "plan_key": order.plan_key,
        "period_months": order.period_months,
        "payment_url": order.payment_url,
        "invoice_number": order.invoice_number,
        "payer": {
            "inn": order.payer_inn,
            "kpp": order.payer_kpp,
            "name": order.payer_name,
            "ogrn": order.payer_ogrn,
            "address": order.payer_address,
        },
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "paid_at": order.paid_at.isoformat() if order.paid_at else None,
    }


def _payment_error(code: str, message: str, http_status: int = status.HTTP_400_BAD_REQUEST) -> HTTPException:
    return HTTPException(status_code=http_status, detail={"error": {"code": code, "message": message}})


def _build_purchase(body: PaymentCreateRequest) -> dict[str, Any]:
    if body.purchase_type == "token_topup":
        if not body.token_pack_key:
            raise _payment_error("token_pack_required", "Token pack is required")
        pack = TOKEN_PACK_CATALOG.get(body.token_pack_key)
        if not pack:
            raise _payment_error("unknown_token_pack", "Unknown token pack")
        return {
            "purpose": "token_topup",
            "amount_cents": int(pack["price"]) * 100,
            "token_amount_mtokens": tokens_to_mtokens(int(pack["tokens"])),
            "plan_key": None,
            "period_months": None,
            "title": pack["name"],
            "metadata": {"token_pack_key": body.token_pack_key, "tokens": int(pack["tokens"])},
        }

    if not body.plan_key:
        raise _payment_error("plan_required", "Plan is required")
    plan = PLAN_CATALOG.get(body.plan_key)
    if not plan:
        raise _payment_error("unknown_plan", "Unknown plan")
    months = PERIOD_MONTHS[body.period]
    addon_total = 0
    addon_items = []
    for key in body.addon_keys:
        item = SUBSCRIPTION_MODULE_CATALOG.get(key)
        if not item:
            raise _payment_error("unknown_addon", "Unknown subscription add-on")
        addon_total += int(item["price"])
        addon_items.append({"key": key, "name": item["name"], "monthly_price": int(item["price"])})
    for key in body.sla_keys:
        item = SLA_CATALOG.get(key)
        if not item:
            raise _payment_error("unknown_sla", "Unknown SLA option")
        addon_total += int(item["price"])
        addon_items.append({"key": key, "name": item["name"], "monthly_price": int(item["price"])})
    token_pack_tokens = 0
    if body.token_pack_key:
        pack = TOKEN_PACK_CATALOG.get(body.token_pack_key)
        if not pack:
            raise _payment_error("unknown_token_pack", "Unknown token pack")
        addon_total += int(pack["price"])
        token_pack_tokens = int(pack["tokens"])
        addon_items.append({"key": body.token_pack_key, "name": pack["name"], "monthly_price": int(pack["price"])})
    discount = 0.2 if body.period == "year" else 0.1 if body.period == "six" else 0.0
    monthly_after_discount = round((int(plan["prices"]["monthly"]) + addon_total) * (1 - discount))
    price_rub = monthly_after_discount * months
    return {
        "purpose": "subscription",
        "amount_cents": price_rub * 100,
        "token_amount_mtokens": tokens_to_mtokens((int(plan["tokens"]) + token_pack_tokens) * months),
        "plan_key": body.plan_key,
        "period_months": months,
        "title": f"CODE9 {plan['name']} на {months} мес.",
        "metadata": {
            "period": body.period,
            "plan_name": plan["name"],
            "monthly_tokens": int(plan["tokens"]),
            "token_pack_monthly_tokens": token_pack_tokens,
            "addon_items": addon_items,
            "discount": discount,
        },
    }


def compute_tbank_token(payload: dict[str, Any], password: str) -> str:
    token_source: dict[str, str] = {"Password": password}
    for key, value in payload.items():
        if key == "Token" or value is None or isinstance(value, (dict, list)):
            continue
        token_source[key] = str(value)
    raw = "".join(token_source[key] for key in sorted(token_source))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _require_tbank_config() -> None:
    if not settings.tbank_eacq_terminal_key or not settings.tbank_eacq_password:
        raise _payment_error(
            "tbank_not_configured",
            "T-Bank acquiring is not configured",
            status.HTTP_501_NOT_IMPLEMENTED,
        )


def _make_external_order_id(workspace_id: uuid.UUID) -> str:
    return f"code9-{str(workspace_id)[:8]}-{uuid.uuid4().hex[:16]}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _get_or_create_billing_account(session: AsyncSession, ws: Workspace) -> BillingAccount:
    ba = (
        await session.execute(select(BillingAccount).where(BillingAccount.workspace_id == ws.id))
    ).scalar_one_or_none()
    if ba:
        return ba
    ba = BillingAccount(workspace_id=ws.id, provider="manual")
    session.add(ba)
    await session.flush()
    return ba


async def apply_paid_payment_order(
    session: AsyncSession,
    order: PaymentOrder,
    *,
    provider_payload: dict[str, Any] | None = None,
) -> None:
    """Apply a successful provider payment exactly once; repeated webhooks are idempotent."""
    if order.status == "paid":
        return
    ws = (
        await session.execute(select(Workspace).where(Workspace.id == order.workspace_id))
    ).scalar_one_or_none()
    if not ws:
        raise _payment_error("workspace_not_found", "Workspace not found", status.HTTP_404_NOT_FOUND)

    ba = await _get_or_create_billing_account(session, ws)
    ba.balance_cents = int(ba.balance_cents or 0) + int(order.amount_cents or 0)
    if order.plan_key:
        ba.plan = order.plan_key
    session.add(
        BillingLedger(
            billing_account_id=ba.id,
            workspace_id=ws.id,
            amount_cents=int(order.amount_cents or 0),
            currency=order.currency,
            kind="deposit",
            reference=f"payment_order:{order.id}",
            description="Оплата CODE9" if order.purpose == "subscription" else "Пополнение AIC9 токенов",
            metadata_json={"payment_order_id": str(order.id), "provider": order.provider},
        )
    )

    if int(order.token_amount_mtokens or 0) > 0:
        account = await credit_tokens(
            session,
            workspace=ws,
            amount_mtokens=int(order.token_amount_mtokens),
            description=(
                "Токены по тарифу CODE9"
                if order.purpose == "subscription"
                else "Покупка AIC9 токенов"
            ),
            reference=f"payment_order:{order.id}",
            kind="purchase",
            metadata={"payment_order_id": str(order.id), "purpose": order.purpose},
        )
        if order.plan_key:
            account.plan_key = order.plan_key
            account.included_monthly_mtokens = tokens_to_mtokens(
                int(PLAN_CATALOG.get(order.plan_key, {}).get("tokens", 0))
            )
            base = account.subscription_expires_at if account.subscription_expires_at and account.subscription_expires_at > _now() else _now()
            account.subscription_expires_at = base + timedelta(days=30 * int(order.period_months or 1))

    order.status = "paid"
    order.paid_at = _now()
    metadata = dict(order.metadata_json or {})
    metadata["provider_payload"] = provider_payload or {}
    order.metadata_json = metadata


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


@router.get("/workspaces/{workspace_id}/billing/token-account")
async def get_workspace_token_account(
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    ws = await _load_ws(session, workspace_id, user)
    account = await get_or_create_token_account(session, ws)
    await session.commit()
    return token_account_snapshot(account)


@router.get("/workspaces/{workspace_id}/billing/account")
async def get_workspace_billing_account(
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    ws = await _load_ws(session, workspace_id, user)
    ba = await _get_or_create_billing_account(session, ws)
    await session.commit()
    return _serialize_billing_account(ba)


@router.get("/workspaces/{workspace_id}/billing/ledger")
async def get_workspace_billing_ledger(
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    ws = await _load_ws(session, workspace_id, user)
    ba = await _get_or_create_billing_account(session, ws)
    rows = (
        await session.execute(
            select(BillingLedger)
            .where(BillingLedger.billing_account_id == ba.id)
            .order_by(BillingLedger.created_at.desc())
            .limit(100)
        )
    ).scalars().all()
    await session.commit()
    return {"items": [_serialize_billing_ledger(row) for row in rows]}


@router.get("/workspaces/{workspace_id}/billing/token-ledger")
async def get_workspace_token_ledger(
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await _load_ws(session, workspace_id, user)
    account = await get_or_create_token_account(
        session,
        (await session.execute(select(Workspace).where(Workspace.id == workspace_id))).scalar_one(),
    )
    rows = (
        await session.execute(
            select(TokenLedger)
            .where(TokenLedger.token_account_id == account.id)
            .order_by(TokenLedger.created_at.desc())
            .limit(100)
        )
    ).scalars().all()
    await session.commit()
    return {"items": [_serialize_token_ledger(row) for row in rows]}


@router.post("/workspaces/{workspace_id}/billing/dadata/party-suggest")
async def suggest_party_by_inn(
    workspace_id: uuid.UUID,
    body: PartySuggestRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await _load_ws(session, workspace_id, user)
    if not settings.dadata_api_key:
        raise _payment_error(
            "dadata_not_configured",
            "DaData is not configured",
            status.HTTP_501_NOT_IMPLEMENTED,
        )
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                settings.dadata_api_url,
                headers={
                    "Authorization": f"Token {settings.dadata_api_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json={"query": body.query, "count": body.count},
            )
            resp.raise_for_status()
    except httpx.HTTPError:
        raise _payment_error("dadata_unavailable", "DaData request failed", status.HTTP_502_BAD_GATEWAY) from None

    suggestions = []
    for item in (resp.json().get("suggestions") or [])[: body.count]:
        data = item.get("data") or {}
        name = data.get("name") or {}
        address = data.get("address") or {}
        suggestions.append(
            {
                "value": item.get("value"),
                "unrestricted_value": item.get("unrestricted_value"),
                "inn": data.get("inn"),
                "kpp": data.get("kpp"),
                "ogrn": data.get("ogrn"),
                "name": name.get("full_with_opf") or name.get("short_with_opf") or item.get("value"),
                "address": address.get("unrestricted_value") or address.get("value"),
            }
        )
    return {"items": suggestions}


async def _create_payment_order(
    session: AsyncSession,
    *,
    ws: Workspace,
    user: User,
    body: PaymentCreateRequest,
    method: str,
) -> PaymentOrder:
    purchase = _build_purchase(body)
    payer = body.payer
    order = PaymentOrder(
        workspace_id=ws.id,
        created_by_user_id=user.id,
        provider="tbank" if method == "card" else "manual_invoice",
        method=method,
        purpose=purchase["purpose"],
        status="pending" if method == "card" else "manual_review",
        amount_cents=purchase["amount_cents"],
        currency="RUB",
        token_amount_mtokens=purchase["token_amount_mtokens"],
        plan_key=purchase["plan_key"],
        period_months=purchase["period_months"],
        external_order_id=_make_external_order_id(ws.id),
        payer_inn=payer.inn if payer else None,
        payer_kpp=payer.kpp if payer else None,
        payer_name=payer.name if payer else None,
        payer_ogrn=payer.ogrn if payer else None,
        payer_address=payer.address if payer else None,
        metadata_json={"purchase": purchase["metadata"], "title": purchase["title"]},
    )
    if method == "invoice":
        order.invoice_number = f"CODE9-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    session.add(order)
    await session.flush()
    return order


@router.post("/workspaces/{workspace_id}/billing/payments/card")
async def create_card_payment(
    workspace_id: uuid.UUID,
    body: PaymentCreateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    _require_tbank_config()
    ws = await _load_ws(session, workspace_id, user)
    order = await _create_payment_order(session, ws=ws, user=user, body=body, method="card")
    title = (order.metadata_json or {}).get("title") or "CODE9 payment"
    init_payload: dict[str, Any] = {
        "TerminalKey": settings.tbank_eacq_terminal_key,
        "Amount": int(order.amount_cents),
        "OrderId": order.external_order_id,
        "Description": title,
        "NotificationURL": f"{settings.base_url.rstrip('/')}/api/v1/billing/tbank/notifications",
    }
    if settings.tbank_eacq_success_url:
        init_payload["SuccessURL"] = settings.tbank_eacq_success_url
    if settings.tbank_eacq_fail_url:
        init_payload["FailURL"] = settings.tbank_eacq_fail_url
    init_payload["DATA"] = {"workspace_id": str(ws.id), "payment_order_id": str(order.id)}
    init_payload["Token"] = compute_tbank_token(init_payload, settings.tbank_eacq_password)

    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.post(f"{settings.tbank_eacq_api_url.rstrip('/')}/Init", json=init_payload)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError:
        raise _payment_error("tbank_unavailable", "T-Bank acquiring request failed", status.HTTP_502_BAD_GATEWAY) from None

    if not data.get("Success"):
        message = str(data.get("Message") or data.get("Details") or "T-Bank payment init failed")
        raise _payment_error("tbank_init_failed", message, status.HTTP_502_BAD_GATEWAY)

    order.external_payment_id = str(data.get("PaymentId") or "")
    order.payment_url = data.get("PaymentURL")
    metadata = dict(order.metadata_json or {})
    metadata["tbank_init"] = {
        "success": bool(data.get("Success")),
        "status": data.get("Status"),
        "payment_id": data.get("PaymentId"),
    }
    order.metadata_json = metadata
    await session.commit()
    return {"order": _serialize_payment_order(order), "payment_url": order.payment_url}


@router.post("/workspaces/{workspace_id}/billing/payments/invoice")
async def create_invoice_payment(
    workspace_id: uuid.UUID,
    body: PaymentCreateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    if not body.payer:
        raise _payment_error("payer_required", "Company details are required for invoice")
    ws = await _load_ws(session, workspace_id, user)
    order = await _create_payment_order(session, ws=ws, user=user, body=body, method="invoice")
    await session.commit()
    return {
        "order": _serialize_payment_order(order),
        "message": "Счёт сформирован как заявка. Оплата по счёту подтверждается администратором.",
    }


@router.get("/workspaces/{workspace_id}/billing/payments/{order_id}")
async def get_payment_order(
    workspace_id: uuid.UUID,
    order_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await _load_ws(session, workspace_id, user)
    order = (
        await session.execute(
            select(PaymentOrder)
            .where(PaymentOrder.id == order_id)
            .where(PaymentOrder.workspace_id == workspace_id)
        )
    ).scalar_one_or_none()
    if not order:
        raise _payment_error("payment_order_not_found", "Payment order not found", status.HTTP_404_NOT_FOUND)
    return _serialize_payment_order(order)


@router.post("/billing/tbank/notifications")
async def tbank_notifications(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Response:
    if not settings.tbank_eacq_password:
        raise _payment_error(
            "tbank_webhook_not_configured",
            "T-Bank notification password is not configured",
            status.HTTP_501_NOT_IMPLEMENTED,
        )
    if request.headers.get("content-type", "").startswith("application/json"):
        payload = await request.json()
    else:
        form = await request.form()
        payload = dict(form)

    expected = compute_tbank_token(payload, settings.tbank_eacq_password)
    if payload.get("Token") != expected:
        raise _payment_error("bad_tbank_token", "Invalid payment notification token", status.HTTP_403_FORBIDDEN)

    external_order_id = payload.get("OrderId")
    if not external_order_id:
        raise _payment_error("missing_order_id", "Missing OrderId")
    order = (
        await session.execute(
            select(PaymentOrder).where(PaymentOrder.external_order_id == str(external_order_id))
        )
    ).scalar_one_or_none()
    if not order:
        raise _payment_error("payment_order_not_found", "Payment order not found", status.HTTP_404_NOT_FOUND)
    if order.provider != "tbank":
        raise _payment_error("payment_order_not_found", "Payment order not found", status.HTTP_404_NOT_FOUND)

    provider_status = str(payload.get("Status") or "").upper()
    if provider_status == "CONFIRMED":
        await apply_paid_payment_order(session, order, provider_payload={"status": provider_status})
    elif provider_status in {"REJECTED", "CANCELED", "DEADLINE_EXPIRED", "AUTH_FAIL"}:
        order.status = "failed" if provider_status != "CANCELED" else "cancelled"
        metadata = dict(order.metadata_json or {})
        metadata["last_provider_status"] = provider_status
        order.metadata_json = metadata
    else:
        metadata = dict(order.metadata_json or {})
        metadata["last_provider_status"] = provider_status
        order.metadata_json = metadata

    await session.commit()
    return Response(content="OK", media_type="text/plain")


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
