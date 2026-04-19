"""
Fernet wrapper для шифрования CRM OAuth-токенов at-rest — API-сторона.

Мы держим отдельный модуль в API (а не импортируем из worker'а), потому что:

* API и worker — отдельные сервисы в compose'е, их PYTHONPATH не пересекается
  (``/packages/ai/src:/packages/crm-connectors/src`` — но НЕ ``/app/worker``).
* Дублирование минимальное (~15 строк), а связность пакетов остаётся чистой.

Ключ (``FERNET_KEY``) читается из того же env, что и в worker'е, поэтому
токены, зашифрованные в API на OAuth-callback'е, читаются worker'ом без
миграций — пара зашифровано-тут-расшифровано-там работает из коробки.

См. ``apps/worker/worker/lib/crypto.py`` — зеркальный модуль для worker'а.
Security review, ``docs/qa/SECURITY_REVIEW.md §1.2``.
"""
from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet

from app.core.settings import get_settings


class FernetKeyMissingError(RuntimeError):
    """``FERNET_KEY`` не задан / некорректен."""


@lru_cache(maxsize=1)
def get_token_cipher() -> Fernet:
    """
    Синглтон Fernet. Бросает FernetKeyMissingError если в Settings пусто.

    В prod-валидаторе ``Settings.check_prod_secrets`` уже отловит дефолтный
    ключ; эта проверка остаётся последней линией обороны на случай dev
    окружений с ``FERNET_KEY=""``.
    """
    key = (get_settings().fernet_key or "").strip()
    if not key:
        raise FernetKeyMissingError(
            "FERNET_KEY не задан. Сгенерировать: python -c "
            "'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
        )
    try:
        return Fernet(key.encode("utf-8") if isinstance(key, str) else key)
    except Exception as exc:  # pragma: no cover — ловит битый key однократно
        raise FernetKeyMissingError(
            f"FERNET_KEY invalid: {type(exc).__name__}. "
            "Ожидается 32-байтный URL-safe base64 ключ."
        ) from None


def encrypt_token(plain: str) -> bytes:
    """Зашифровать строковый токен → BYTEA-совместимые bytes."""
    return get_token_cipher().encrypt(plain.encode("utf-8"))


def decrypt_token(ciphertext: bytes) -> str:
    """Расшифровать BYTEA → str."""
    return get_token_cipher().decrypt(bytes(ciphertext)).decode("utf-8")


def reset_cipher_cache() -> None:
    """Для тестов: сбросить lru_cache."""
    get_token_cipher.cache_clear()


__all__ = [
    "FernetKeyMissingError",
    "get_token_cipher",
    "encrypt_token",
    "decrypt_token",
    "reset_cipher_cache",
]
