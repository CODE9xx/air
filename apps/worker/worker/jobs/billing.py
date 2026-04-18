"""
Billing jobs: monthly charge, usage charge, recalc balance, issue invoice.

В MVP вся внешняя интеграция (YooKassa/Stripe) — заглушки. Мы пишем
только во внутренний ledger и пересчитываем ``billing_accounts.balance_cents``.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text

from ..lib.db import sync_session
from ._common import mark_job_failed, mark_job_running, mark_job_succeeded


def recalc_balance(
    billing_account_id: str,
    *,
    job_row_id: str | None = None,
) -> dict[str, Any]:
    """
    Пересчитать ``balance_cents`` как SUM(billing_ledger.amount_cents).

    Idempotent, безопасно вызывать при любых расхождениях.
    """
    mark_job_running(job_row_id)
    try:
        with sync_session() as sess:
            row = sess.execute(
                text(
                    "SELECT COALESCE(SUM(amount_cents),0) FROM billing_ledger "
                    "WHERE billing_account_id = CAST(:aid AS UUID)"
                ),
                {"aid": billing_account_id},
            ).fetchone()
            new_balance = int(row[0] if row else 0)

            sess.execute(
                text(
                    "UPDATE billing_accounts SET balance_cents=:bal, updated_at=NOW() "
                    "WHERE id = CAST(:aid AS UUID)"
                ),
                {"bal": new_balance, "aid": billing_account_id},
            )

        result = {"billing_account_id": billing_account_id, "balance_cents": new_balance}
        mark_job_succeeded(job_row_id, result)
        return result
    except Exception as exc:
        mark_job_failed(job_row_id, f"recalc_balance: {exc}")
        raise


def billing_monthly_charge(
    workspace_id: str,
    *,
    amount_cents: int = 0,
    description: str = "Ежемесячная абонплата",
    job_row_id: str | None = None,
) -> dict[str, Any]:
    """Записать charge в ledger и пересчитать balance."""
    mark_job_running(job_row_id)
    try:
        with sync_session() as sess:
            acc = sess.execute(
                text(
                    "SELECT id, currency FROM billing_accounts "
                    "WHERE workspace_id = CAST(:wid AS UUID)"
                ),
                {"wid": workspace_id},
            ).fetchone()
            if acc is None:
                raise RuntimeError(f"billing_accounts не найден для ws={workspace_id}")
            account_id, currency = str(acc[0]), acc[1]

            sess.execute(
                text(
                    "INSERT INTO billing_ledger("
                    "  billing_account_id, workspace_id, amount_cents, currency, "
                    "  kind, description, metadata) "
                    "VALUES (CAST(:aid AS UUID), CAST(:wid AS UUID), :amt, :cur, "
                    "        'charge', :d, CAST('{}' AS JSONB))"
                ),
                {
                    "aid": account_id,
                    "wid": workspace_id,
                    "amt": -abs(amount_cents),
                    "cur": currency,
                    "d": description,
                },
            )

        recalc_balance(account_id)
        result = {"workspace_id": workspace_id, "charged_cents": amount_cents}
        mark_job_succeeded(job_row_id, result)
        return result
    except Exception as exc:
        mark_job_failed(job_row_id, f"billing_monthly_charge: {exc}")
        raise


def billing_usage_charge(
    workspace_id: str,
    *,
    amount_cents: int,
    reference: str | None = None,
    description: str = "Usage",
    job_row_id: str | None = None,
) -> dict[str, Any]:
    """Charge по факту использования (AI, экспорт и т.п.)."""
    mark_job_running(job_row_id)
    try:
        with sync_session() as sess:
            acc = sess.execute(
                text(
                    "SELECT id, currency FROM billing_accounts "
                    "WHERE workspace_id = CAST(:wid AS UUID)"
                ),
                {"wid": workspace_id},
            ).fetchone()
            if acc is None:
                raise RuntimeError(f"billing_accounts не найден для ws={workspace_id}")
            account_id, currency = str(acc[0]), acc[1]
            sess.execute(
                text(
                    "INSERT INTO billing_ledger("
                    "  billing_account_id, workspace_id, amount_cents, currency, "
                    "  kind, reference, description, metadata) "
                    "VALUES (CAST(:aid AS UUID), CAST(:wid AS UUID), :amt, :cur, "
                    "        'charge', :ref, :d, CAST('{}' AS JSONB))"
                ),
                {
                    "aid": account_id,
                    "wid": workspace_id,
                    "amt": -abs(amount_cents),
                    "cur": currency,
                    "ref": reference,
                    "d": description,
                },
            )
        recalc_balance(account_id)
        result = {"workspace_id": workspace_id, "charged_cents": amount_cents}
        mark_job_succeeded(job_row_id, result)
        return result
    except Exception as exc:
        mark_job_failed(job_row_id, f"billing_usage_charge: {exc}")
        raise


def issue_invoice(
    workspace_id: str,
    *,
    amount_cents: int,
    job_row_id: str | None = None,
) -> dict[str, Any]:
    """MVP-заглушка: логирует намерение выставить счёт и пишет notification."""
    mark_job_running(job_row_id)
    try:
        with sync_session() as sess:
            sess.execute(
                text(
                    "INSERT INTO notifications(workspace_id, kind, title, body, metadata) "
                    "VALUES (CAST(:wid AS UUID), 'billing_low', 'Счёт выставлен (mock)', "
                    "        'Оплатите счёт для продолжения работы.', "
                    "        CAST(:meta AS JSONB))"
                ),
                {
                    "wid": workspace_id,
                    "meta": f'{{"amount_cents":{amount_cents}}}',
                },
            )
        result = {"workspace_id": workspace_id, "amount_cents": amount_cents, "mock": True}
        mark_job_succeeded(job_row_id, result)
        return result
    except Exception as exc:
        mark_job_failed(job_row_id, f"issue_invoice: {exc}")
        raise
