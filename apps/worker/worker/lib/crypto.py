"""
Fernet wrapper для шифрования CRM OAuth-токенов at-rest.

См. ``docs/security/OAUTH_TOKENS.md``:
- Ключ читается из ENV ``FERNET_KEY`` (Fernet.generate_key()).
- Шифрование выполняется ТОЛЬКО в worker'е (не в API request cycle).
- Токены хранятся в ``crm_connections.access_token_encrypted / refresh_token_encrypted``
  как BYTEA.
"""
from __future__ import annotations

import os
from functools import lru_cache

from cryptography.fernet import Fernet


class FernetKeyMissingError(RuntimeError):
    """``FERNET_KEY`` не задан в окружении."""


@lru_cache(maxsize=1)
def get_token_cipher() -> Fernet:
    """Синглтон Fernet. Бросает FernetKeyMissingError если нет ENV."""
    key = os.getenv("FERNET_KEY")
    if not key:
        raise FernetKeyMissingError(
            "FERNET_KEY не задан. Сгенерировать: "
            "python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_token(plain: str) -> bytes:
    """Зашифровать строковый токен → BYTEA-совместимые bytes."""
    return get_token_cipher().encrypt(plain.encode("utf-8"))


def decrypt_token(ciphertext: bytes) -> str:
    """Расшифровать BYTEA → str."""
    return get_token_cipher().decrypt(bytes(ciphertext)).decode("utf-8")
