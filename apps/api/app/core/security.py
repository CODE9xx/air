"""
Security helpers:
  * argon2id хеширование (паролей, refresh-токенов, email-кодов);
  * JWT encode/decode (HS256, 15 min для access);
  * генерация opaque refresh-токенов и numeric кодов.
"""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from jose import JWTError, jwt

from app.core.settings import get_settings

# argon2id с параметрами из docs/security/AUTH.md
_password_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=64 * 1024,
    parallelism=2,
)


# --------- Пароли / refresh-токены / email-коды (argon2id) ---------

def hash_secret(value: str) -> str:
    """Хешируем строку (пароль / opaque-токен / email-код) argon2id."""
    return _password_hasher.hash(value)


def verify_secret(hashed: str, plain: str) -> bool:
    """Проверка argon2-хеша. Возвращает False вместо исключения."""
    try:
        return _password_hasher.verify(hashed, plain)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def needs_rehash(hashed: str) -> bool:
    """Сообщает, нужно ли пере-хешировать (если параметры argon2 поменялись)."""
    try:
        return _password_hasher.check_needs_rehash(hashed)
    except Exception:
        return False


# --------- Refresh-токены ---------

def generate_refresh_token() -> str:
    """Opaque refresh-token (≥64 символов)."""
    return secrets.token_urlsafe(48)


def build_session_cookie(session_id: str, opaque: str) -> str:
    """Cookie value формата `<session_id>.<opaque>` (см. AUTH.md §3)."""
    return f"{session_id}.{opaque}"


def split_session_cookie(cookie_value: str) -> tuple[str, str] | None:
    """Парсит cookie `<session_id>.<opaque>` → (session_id, opaque). None при ошибке."""
    if not cookie_value or "." not in cookie_value:
        return None
    sid, _, opaque = cookie_value.partition(".")
    if not sid or not opaque:
        return None
    return sid, opaque


# --------- Email-коды ---------

def generate_email_code() -> str:
    """6-значный numeric код (000000-999999)."""
    return "".join(str(secrets.randbelow(10)) for _ in range(6))


# --------- JWT ---------

ScopeT = Literal["user", "admin"]


def create_access_token(
    subject: str,
    scope: ScopeT = "user",
    extra_claims: dict[str, Any] | None = None,
) -> tuple[str, int]:
    """
    Выпускает access JWT (HS256, 15 min). Для admin-scope — другой secret.

    Возвращает (token, expires_in_seconds).
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)
    ttl = settings.access_token_ttl_seconds
    payload: dict[str, Any] = {
        "sub": subject,
        "scope": scope,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl)).timestamp()),
        "jti": str(uuid.uuid4()),
    }
    if extra_claims:
        payload.update(extra_claims)
    secret = settings.admin_jwt_secret if scope == "admin" else settings.jwt_secret
    token = jwt.encode(payload, secret, algorithm=settings.jwt_algorithm)
    return token, ttl


def decode_token(token: str, scope: ScopeT = "user") -> dict[str, Any] | None:
    """Декодируем JWT. None при невалидной подписи / просрочке."""
    settings = get_settings()
    secret = settings.admin_jwt_secret if scope == "admin" else settings.jwt_secret
    try:
        payload = jwt.decode(token, secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None
    if payload.get("scope") != scope:
        return None
    return payload
