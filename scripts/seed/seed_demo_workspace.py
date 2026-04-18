"""
seed_demo_workspace — создать демо-юзера + workspace + mock CRM-подключение.

Удобно для QA/FE, чтобы иметь рабочий состояние БД сразу после bootstrap.

Читает из окружения:
  * ``DEMO_USER_EMAIL`` (default ``demo@code9.local``);
  * ``DEMO_USER_PASSWORD`` (default ``demo12345``, только для dev);
  * ``DEMO_WORKSPACE_NAME`` (default ``Demo Workspace``);
  * ``DEMO_WORKSPACE_SLUG`` (default ``demo-ws``);
  * ``DATABASE_URL``.

Идемпотентно: ищет user/workspace/connection по уникальным ключам и либо
создаёт, либо оставляет как есть.

Запуск:
    python -m scripts.seed.seed_demo_workspace
"""
from __future__ import annotations

import os
import sys

from argon2 import PasswordHasher
from sqlalchemy import create_engine, text


def _sync_url() -> str:
    url = os.getenv("DATABASE_URL", "postgresql://code9:code9@postgres:5432/code9")
    return (
        url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
        .replace("postgres+asyncpg://", "postgresql+psycopg2://")
    )


def _hash(plain: str) -> str:
    return PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=2).hash(plain)


def seed_demo() -> dict[str, str]:
    email = os.getenv("DEMO_USER_EMAIL", "demo@code9.local").strip().lower()
    password = os.getenv("DEMO_USER_PASSWORD", "demo12345")
    ws_name = os.getenv("DEMO_WORKSPACE_NAME", "Demo Workspace")
    ws_slug = os.getenv("DEMO_WORKSPACE_SLUG", "demo-ws")

    engine = create_engine(_sync_url(), future=True)
    try:
        with engine.begin() as conn:
            # --- User ------------------------------------------------------
            row = conn.execute(
                text("SELECT id FROM users WHERE email = :e"),
                {"e": email},
            ).fetchone()
            if row is None:
                user_id = conn.execute(
                    text(
                        "INSERT INTO users("
                        "  email, password_hash, display_name, locale, "
                        "  email_verified_at, status) "
                        "VALUES (:e, :p, :dn, 'ru', NOW(), 'active') "
                        "RETURNING id"
                    ),
                    {"e": email, "p": _hash(password), "dn": "Demo User"},
                ).scalar_one()
            else:
                user_id = row[0]

            # --- Workspace ------------------------------------------------
            row = conn.execute(
                text("SELECT id FROM workspaces WHERE slug = :s"),
                {"s": ws_slug},
            ).fetchone()
            if row is None:
                workspace_id = conn.execute(
                    text(
                        "INSERT INTO workspaces("
                        "  name, slug, owner_user_id, locale, status) "
                        "VALUES (:n, :s, :oid, 'ru', 'active') "
                        "RETURNING id"
                    ),
                    {"n": ws_name, "s": ws_slug, "oid": str(user_id)},
                ).scalar_one()
            else:
                workspace_id = row[0]

            # --- Workspace member (owner) ---------------------------------
            conn.execute(
                text(
                    "INSERT INTO workspace_members("
                    "  workspace_id, user_id, role, accepted_at) "
                    "VALUES (:ws, :u, 'owner', NOW()) "
                    "ON CONFLICT (workspace_id, user_id) DO NOTHING"
                ),
                {"ws": str(workspace_id), "u": str(user_id)},
            )

            # --- Billing account ------------------------------------------
            conn.execute(
                text(
                    "INSERT INTO billing_accounts("
                    "  workspace_id, currency, balance_cents, plan, provider) "
                    "VALUES (:ws, 'RUB', 0, 'free', 'manual') "
                    "ON CONFLICT (workspace_id) DO NOTHING"
                ),
                {"ws": str(workspace_id)},
            )

            # --- CRM connection (mock, pending) ---------------------------
            row = conn.execute(
                text(
                    "SELECT id FROM crm_connections "
                    "WHERE workspace_id = :ws AND provider = 'amocrm' "
                    "AND status != 'deleted' LIMIT 1"
                ),
                {"ws": str(workspace_id)},
            ).fetchone()
            if row is None:
                connection_id = conn.execute(
                    text(
                        "INSERT INTO crm_connections("
                        "  workspace_id, provider, external_domain, status, metadata) "
                        "VALUES (:ws, 'amocrm', 'demo.amocrm.ru', 'pending', "
                        "        CAST('{\"mock\":true}' AS JSONB)) "
                        "RETURNING id"
                    ),
                    {"ws": str(workspace_id)},
                ).scalar_one()
            else:
                connection_id = row[0]

    finally:
        engine.dispose()

    return {
        "user_id": str(user_id),
        "workspace_id": str(workspace_id),
        "workspace_slug": ws_slug,
        "connection_id": str(connection_id),
        "email": email,
    }


def main() -> int:
    try:
        summary = seed_demo()
    except Exception as exc:
        print(f"[seed_demo_workspace] ошибка: {exc}", file=sys.stderr)
        return 1
    print(
        "[seed_demo_workspace] ok: "
        f"user={summary['email']} ws={summary['workspace_slug']} "
        f"connection={summary['connection_id']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
