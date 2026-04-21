"""
amoCRM OAuth client credentials resolver (Task #52.3F, Bug F).

Worker-jobs (``pull_amocrm_core`` / ``refresh_token``) исторически читали
client_id / client_secret из env ``AMOCRM_CLIENT_ID`` / ``AMOCRM_CLIENT_SECRET``
вне зависимости от режима подключения. Для режима ``external_button``
(#44.6) это неверно: у каждого ``crm_connection`` своя пара credentials,
которую amoCRM присылает вебхуком и кладёт в
``crm_connections.amocrm_client_id`` + ``amocrm_client_secret_encrypted``
(Fernet). Глобальные env для external_button должны оставаться пустыми —
попытка взять их привела бы к «AMOCRM_CLIENT_ID не заданы» (Bug F) либо,
хуже, к использованию чужих credentials на чужом аккаунте.

Контракт helper'а:

    load_amocrm_oauth_credentials(conn_row, *, connection_id)
        -> (client_id: str, client_secret: str)

где ``conn_row`` — dict / Mapping с полями:

    amocrm_auth_mode              : str | None     # 'static_client' | 'external_button' | None
    amocrm_client_id              : str | None
    amocrm_client_secret_encrypted: bytes | None

Поведение по режиму:

* ``external_button`` — строго per-installation. Если ``client_id``
  или ``client_secret_encrypted`` пустые — ``AmoCredentialsMissingError``;
  **без** fallback на env. Иначе — Fernet-дешифровка in-memory.
* ``static_client`` / ``None`` / пусто — legacy / pre-#44.6 подключения:
  глобальные ``AMOCRM_CLIENT_ID`` + ``AMOCRM_CLIENT_SECRET`` из env.

Безопасность:

* Plaintext client_secret НЕ попадает ни в logger.info/warning/error,
  ни в текст исключений. В логи идёт только ``connection_id`` +
  ``auth_mode``; в сообщениях исключений — только ``connection_id``.
* Fernet-ошибки расшифровки оборачиваются в
  ``AmoCredentialsDecryptError`` через ``raise ... from None``, чтобы
  оригинальный traceback (который Fernet умеет приправлять токеном
  в редких случаях) не утёк в worker stderr / Redis.
* static_client mode: если env пустые — поднимаем ``RuntimeError``
  с коротким сообщением без подстановки reveal-значений.

Тесты: ``tests/api/test_amocrm_worker_credentials.py`` (6 cases).
"""
from __future__ import annotations

import logging
import os
from typing import Mapping

from .crypto import decrypt_token

logger = logging.getLogger("code9.worker.amocrm_creds")


class AmoCredentialsMissingError(RuntimeError):
    """external_button: per-connection client_id/secret отсутствуют в БД."""


class AmoCredentialsDecryptError(RuntimeError):
    """external_button: Fernet.decrypt провалился на client_secret_encrypted."""


def _mode_of(conn_row: Mapping[str, object]) -> str:
    raw = conn_row.get("amocrm_auth_mode")
    if not raw:
        return "static_client"
    mode = str(raw).strip().lower()
    return mode or "static_client"


def load_amocrm_oauth_credentials(
    conn_row: Mapping[str, object],
    *,
    connection_id: str,
) -> tuple[str, str]:
    """
    Вернуть (client_id, client_secret) для worker-job'а.

    См. docstring модуля для полного контракта.

    Raises:
        AmoCredentialsMissingError: external_button, но per-install creds пусты.
        AmoCredentialsDecryptError: external_button, Fernet не смог decrypt.
        RuntimeError: static_client, env ``AMOCRM_CLIENT_ID/SECRET`` пусты.
    """
    mode = _mode_of(conn_row)

    if mode == "external_button":
        client_id_val = conn_row.get("amocrm_client_id") or ""
        client_id = str(client_id_val).strip() if client_id_val else ""
        encrypted = conn_row.get("amocrm_client_secret_encrypted")
        if not client_id or not encrypted:
            logger.error(
                "amocrm_creds_missing",
                extra={
                    "connection_id": connection_id,
                    "auth_mode": mode,
                    "has_client_id": bool(client_id),
                    "has_client_secret": bool(encrypted),
                },
            )
            raise AmoCredentialsMissingError(
                "amoCRM external_button credentials не найдены для "
                f"connection_id={connection_id}: client_id и/или "
                "client_secret_encrypted пусты в crm_connections. "
                "Не fallback'аемся на env — это предотвращает утечку "
                "глобальных credentials в чужой аккаунт."
            )
        try:
            client_secret = decrypt_token(encrypted)  # type: ignore[arg-type]
        except Exception as exc:
            logger.error(
                "amocrm_creds_decrypt_failed",
                extra={
                    "connection_id": connection_id,
                    "error_type": type(exc).__name__,
                },
            )
            # ``from None`` подавляет оригинальный Fernet traceback —
            # не хотим, чтобы потенциальные внутренние поля токена
            # утекли в worker stderr / RQ exc_info.
            raise AmoCredentialsDecryptError(
                "amoCRM external_button: Fernet-дешифровка "
                f"client_secret_encrypted провалилась для "
                f"connection_id={connection_id}"
            ) from None
        return client_id, client_secret

    # static_client / NULL / '' — legacy / pre-#44.6.
    env_id = os.getenv("AMOCRM_CLIENT_ID", "") or ""
    env_secret = os.getenv("AMOCRM_CLIENT_SECRET", "") or ""
    if not env_id or not env_secret:
        # Не логируем значения — даже пустые, чтобы случайный reveal-
        # патчер не подставил что-нибудь в extra.
        logger.error(
            "amocrm_creds_env_missing",
            extra={"connection_id": connection_id, "auth_mode": mode},
        )
        raise RuntimeError(
            "amoCRM static_client: AMOCRM_CLIENT_ID / AMOCRM_CLIENT_SECRET "
            "не заданы в worker env (connection_id=" + connection_id + "). "
            "Для external_button — credentials должны быть сохранены "
            "per-connection при установке интеграции."
        )
    return env_id, env_secret
