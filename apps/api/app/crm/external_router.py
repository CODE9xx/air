"""
amoCRM external_button webhook endpoints (#44.6, v2 per #48.1).

Префикс: `/integrations/amocrm/external/*`.

Доступные роуты:
  * `POST /external/secrets`     — primary (соответствует
    official amoCRM External Integration Button: `data-secrets_uri`).
  * `POST /external/credentials` — legacy alias, тот же handler.

В режиме external_button amoCRM САМ создаёт интеграцию в момент нажатия
клиентом «Подключить» у нас в UI, после чего присылает client_id/secret
вебхуком на наш публичный HTTPS-endpoint. Поведение:

1. Пользователь кликает по кнопке у нас → BE делает /oauth/start, который
   создаёт pending `CrmConnection` и кладёт в Redis state (TTL 10 мин).
2. Фронт рендерит официальный widget amoCRM (script class="amocrm_oauth"),
   передаёт в него наш `state`, `redirect_uri`, `secrets_uri` и остальные
   data-* атрибуты (см. `/oauth/button-config`). По клику клиент
   проваливается в amoCRM, авторизуется, создаёт интеграцию.
3. amoCRM POST'ит на primary endpoint `/external/secrets` (или на legacy
   alias `/external/credentials`) JSON:
   `{"state": "...", "client_id": "...", "client_secret": "...",
     "integration_id": "...", "account_id": 1234567, "account_subdomain": "..."}`.
4. Мы по state находим `CrmConnection`, шифруем secret через Fernet и
   сохраняем в БД (`amocrm_client_id`, `amocrm_client_secret_encrypted`,
   `amocrm_external_integration_id`).
5. ПОСЛЕ этого amoCRM редиректит юзера на наш /oauth/callback?code=...&state=...
   — там уже стандартный exchange_code, но с per-install credentials.

Security:
  * client_secret шифруется Fernet и ТОЛЬКО зашифрованные bytes уходят в БД;
  * endpoint проверяет state (tokens.token_urlsafe 24, ~32 символа) — replay
    невозможен после первой успешной доставки;
  * state хранится ровно один раз; второй POST на тот же state → 409;
  * ВСЁ чувствительное (secret, code) маскируется log_masker'ом,
    но мы и НЕ пишем это в extra={} — логируем лишь префиксы.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import encrypt_token
from app.core.db import get_session
from app.core.redis import get_redis
from app.core.settings import get_settings
from app.crm.oauth_router import (
    _EXTERNAL_PAIRING_PREFIX,
    _EXTERNAL_PAIRING_TTL_SECONDS,
    _OAUTH_STATE_PREFIX,
)
from app.db.models import CrmConnection

router = APIRouter(prefix="/integrations/amocrm/external", tags=["integrations"])
settings = get_settings()

logger = logging.getLogger("code9.integrations.amocrm.external")


class ExternalCredentialsPayload(BaseModel):
    """
    JSON-payload, который amoCRM присылает на /external/credentials.

    Точный формат согласовывается при регистрации external integration
    в amoCRM. Поля обязательны: state + client_id + client_secret;
    остальное — для лога/UX.
    """

    state: str = Field(min_length=8, max_length=128)
    client_id: str = Field(min_length=4, max_length=128)
    client_secret: str = Field(min_length=4, max_length=256)
    integration_id: str | None = Field(default=None, max_length=128)
    account_id: int | None = None
    account_subdomain: str | None = Field(default=None, max_length=128)


@router.post("/secrets", status_code=status.HTTP_200_OK)
@router.post("/credentials", status_code=status.HTTP_200_OK)
async def receive_secrets(
    payload: ExternalCredentialsPayload,
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """
    Webhook от amoCRM: сохраняем per-install client_id/secret в БД.

    Два одинаковых маршрута смотрят на один handler:
      * `POST /external/secrets`     — primary (amoCRM data-secrets_uri, v2).
      * `POST /external/credentials` — legacy alias, поддерживается,
        чтобы старые интеграции, зарегистрированные до #48.1, продолжали
        работать. Фронтам и новым интеграциям следует использовать primary.

    Этот endpoint НЕ требует авторизации (amoCRM не шлёт наш JWT), но:
      * state — нонс из Redis, без него 400;
      * один и тот же state можно "погасить" один раз (second POST → 409);
      * secret шифруется Fernet ПЕРЕД session.commit() — plaintext
        не живёт в БД ни одного момента.

    Поскольку AMOCRM_AUTH_MODE=static_client не должен принимать такие
    webhook'и (секрет статичен), мы в таком режиме возвращаем 404
    (не 400, чтобы не раскрывать конфигурацию).
    """
    auth_mode = (settings.amocrm_auth_mode or "static_client").lower().strip()
    if auth_mode != "external_button":
        logger.info(
            "amocrm_external_webhook_wrong_mode",
            extra={"auth_mode": auth_mode},
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "not_found",
                    "message": "External credentials endpoint is not enabled.",
                }
            },
        )

    redis = get_redis()
    state_key = f"{_OAUTH_STATE_PREFIX}{payload.state}"
    raw_state = await redis.get(state_key)
    if not raw_state:
        # state не найден: либо протух, либо подменён.
        logger.warning(
            "amocrm_external_state_miss",
            extra={"state_prefix": payload.state[:8]},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "invalid_state",
                    "message": "State expired or unknown.",
                }
            },
        )

    # Проверка на replay: если credentials для этого state уже сохранены
    # (pairing-ключ выставлен) — второй webhook отклоняем.
    pairing_key = f"{_EXTERNAL_PAIRING_PREFIX}{payload.state}"
    already_paired = await redis.get(pairing_key)
    if already_paired:
        logger.warning(
            "amocrm_external_replay",
            extra={"state_prefix": payload.state[:8]},
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "already_paired",
                    "message": "Credentials for this state already delivered.",
                }
            },
        )

    try:
        state_payload = json.loads(raw_state)
        connection_id = uuid.UUID(state_payload["connection_id"])
    except (KeyError, ValueError, json.JSONDecodeError):
        logger.error(
            "amocrm_external_state_corrupt",
            extra={"state_prefix": payload.state[:8]},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "invalid_state",
                    "message": "State payload corrupt.",
                }
            },
        )

    conn = (
        await session.execute(
            select(CrmConnection).where(CrmConnection.id == connection_id)
        )
    ).scalar_one_or_none()
    if not conn or conn.provider != "amocrm":
        logger.warning(
            "amocrm_external_conn_missing",
            extra={"connection_id": str(connection_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {"code": "not_found", "message": "Connection not found."}
            },
        )

    # Шифруем secret ДО первой записи в БД.
    try:
        secret_encrypted = encrypt_token(payload.client_secret)
    except Exception as exc:
        logger.error(
            "amocrm_external_encrypt_failed",
            extra={
                "connection_id": str(conn.id),
                "error_type": type(exc).__name__,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": {
                    "code": "internal",
                    "message": "Credential storage failed.",
                }
            },
        )

    conn.amocrm_client_id = payload.client_id
    conn.amocrm_client_secret_encrypted = secret_encrypted
    conn.amocrm_external_integration_id = payload.integration_id
    conn.amocrm_auth_mode = "external_button"
    conn.amocrm_credentials_received_at = datetime.now(timezone.utc)

    # Метаданные (без секретов!) помогают при последующем debug'е.
    existing_meta = dict(conn.metadata_json or {})
    existing_meta["amocrm_external_integration"] = {
        "integration_id": payload.integration_id,
        "account_id": payload.account_id,
        "account_subdomain": payload.account_subdomain,
        "received_at": conn.amocrm_credentials_received_at.isoformat(),
    }
    conn.metadata_json = existing_meta

    # Pairing-ключ защитит от replay: живёт столько же, сколько state.
    await redis.setex(pairing_key, _EXTERNAL_PAIRING_TTL_SECONDS, "1")

    await session.commit()

    logger.info(
        "amocrm_external_credentials_stored",
        extra={
            "connection_id": str(conn.id),
            "integration_id": payload.integration_id,
            "account_id": payload.account_id,
        },
    )
    # Возвращаем HTTP 200 OK с JSON-телом (НЕ 204 No Content).
    #
    # amoCRM external_button flow (#44.6v5 → #51.3):
    #   - Их server-side парсер делает строгую проверку `response.status === 200`.
    #   - Когда мы раньше отдавали 204 No Content, amoCRM в popup'е показывал
    #     «Произошла ошибка создания, обратитесь к разработчику интеграции.
    #      (Code 204)» и НЕ выполнял redirect на redirect_uri?code=...&state=...
    #     То есть integrations успешно сохранялись у нас, но OAuth-flow в amoCRM
    #     не завершался: без redirect callback'а мы не получали authorization
    #     code и не могли обменять на access_token.
    #   - Число «204» в UI-ошибке совпадало с HTTP-статусом нашего ответа —
    #     это и выдало корень: их error message буквально включает status code,
    #     полученный от secrets_uri.
    #
    # Body `{"status": "ok"}` не обязателен по их docs, но:
    #   (a) безопасен (никаких секретов — literal "ok");
    #   (b) даёт диагностический маркер при ручной проверке (curl -i);
    #   (c) некоторые webhook-парсеры падают на нулевом body, поэтому пустой
    #       не-null ответ предпочтительнее.
    return {"status": "ok"}
