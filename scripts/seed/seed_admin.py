"""
seed_admin — создать (или обновить) bootstrap-администратора.

Читает из окружения:
  * ``ADMIN_BOOTSTRAP_EMAIL`` (default ``admin@code9.local``);
  * ``ADMIN_BOOTSTRAP_PASSWORD`` (обязательно должен быть проставлен в проде);
  * ``DATABASE_URL``.

Логика:
1. Если пользователя с таким email **нет** — создаём со role=``superadmin``,
   status=``active``, password_hash=argon2id(password).
2. Если **есть** — обновляем только ``password_hash`` и ``status='active'``
   (чтобы ротация пароля работала).

Идемпотентно. Безопасно запускать повторно.

Запуск:
    docker compose exec api python /app/scripts/seed/seed_admin.py
    # или локально
    python -m scripts.seed.seed_admin
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from argon2 import PasswordHasher
from sqlalchemy import create_engine, text

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _sync_url() -> str:
    """DATABASE_URL → sync (psycopg2) URL."""
    url = os.getenv("DATABASE_URL", "postgresql://code9:code9@postgres:5432/code9")
    return (
        url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
        .replace("postgres+asyncpg://", "postgresql+psycopg2://")
    )


def _hash_password(plain: str) -> str:
    """argon2id hash совместимый с ``apps/api/app/core/security.py``."""
    hasher = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=2)
    return hasher.hash(plain)


def seed_admin(
    email: str | None = None,
    password: str | None = None,
    role: str = "superadmin",
) -> dict[str, str]:
    """Создать или обновить bootstrap-админа. Возвращает summary."""
    email = (email or os.getenv("ADMIN_BOOTSTRAP_EMAIL", "admin@code9.local")).strip().lower()
    password = password or os.getenv("ADMIN_BOOTSTRAP_PASSWORD")
    if not password:
        raise RuntimeError(
            "ADMIN_BOOTSTRAP_PASSWORD не задан в окружении — "
            "сидим admin без пароля запрещено."
        )
    if len(password) < 8:
        raise RuntimeError("ADMIN_BOOTSTRAP_PASSWORD короче 8 символов — отказ.")

    if role not in {"superadmin", "support", "analyst"}:
        raise RuntimeError(f"Недопустимая admin-role: {role!r}")

    password_hash = _hash_password(password)

    engine = create_engine(_sync_url(), future=True)
    try:
        with engine.begin() as conn:
            row = conn.execute(
                text("SELECT id FROM admin_users WHERE email = :email"),
                {"email": email},
            ).fetchone()

            if row is None:
                conn.execute(
                    text(
                        "INSERT INTO admin_users("
                        "  email, password_hash, display_name, role, status) "
                        "VALUES (:email, :pwd, :dn, :role, 'active')"
                    ),
                    {
                        "email": email,
                        "pwd": password_hash,
                        "dn": "Bootstrap Admin",
                        "role": role,
                    },
                )
                action = "created"
            else:
                conn.execute(
                    text(
                        "UPDATE admin_users SET "
                        "  password_hash = :pwd, "
                        "  role = :role, "
                        "  status = 'active', "
                        "  updated_at = NOW() "
                        "WHERE email = :email"
                    ),
                    {"pwd": password_hash, "role": role, "email": email},
                )
                action = "updated"
    finally:
        engine.dispose()

    return {"email": email, "role": role, "action": action}


def main() -> int:
    try:
        summary = seed_admin()
    except Exception as exc:
        print(f"[seed_admin] ошибка: {exc}", file=sys.stderr)
        return 1
    # Пароль НЕ логируем даже в dev — только факт и email.
    print(
        f"[seed_admin] {summary['action']} email={summary['email']} "
        f"role={summary['role']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
