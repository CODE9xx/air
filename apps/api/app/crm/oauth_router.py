"""
Integrations OAuth endpoints — amoCRM (и скелет под kommo/bx24).

Префикс: `/integrations/amocrm/oauth/*`.

При `MOCK_CRM_MODE=true`:
  * `start` — создаёт mock-подключение и редиректит на `/app/connections/<id>`;
  * `callback` — mock всегда успешен.

При `MOCK_CRM_MODE=false` (REAL, Phase 2A):
  * `start`   — создаёт pending CrmConnection, кладёт state (+ ws_id + conn_id)
    в Redis (TTL 10 мин), возвращает ``authorize_url`` (static_client) или
    конфиг кнопки (external_button, #44.6).
  * `callback` — проверяет state, обменивает ``code`` на токены, вызывает
    ``fetch_account`` для subdomain/account_id, шифрует токены (Fernet),
    обновляет CrmConnection в `active` и ставит в очередь
    ``bootstrap_tenant_schema``. Редиректит на ``/app/connections/<id>``.

    В режиме external_button (#44.6) callback ДО обмена кода ждёт
    credentials от webhook — до `amocrm_external_wait_seconds` с
    0.5-секундным backoff'ом. Если не дождались — фейл с
    ``flash=amocrm_credentials_missing``.

Security:
  * state — 24-байтовый ``secrets.token_urlsafe`` (base64 → ~32 символов).
  * redirect_uri в authorize-URL и в exchange_code СТРОГО один и тот же —
    берётся из ``settings.amocrm_redirect_uri``, не из request.
  * Токены шифруются Fernet ПЕРЕД первым commit'ом CrmConnection — в БД
    никогда не попадает plaintext.
  * Per-install client_secret (external_button) так же шифруется Fernet
    ПЕРЕД первой записью в БД — webhook-handler никогда не коммитит plaintext.
  * access_token / refresh_token / code / client_secret (любой!) НЕ логируются.
"""
from __future__ import annotations

import asyncio
import json
import logging
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.crypto import decrypt_token, encrypt_token
from app.core.db import get_session
from app.core.jobs import enqueue, queue_for_kind
from app.core.redis import get_redis
from app.core.settings import get_settings
from app.db.models import CrmConnection, Job, User, Workspace, WorkspaceMember

router = APIRouter(prefix="/integrations/amocrm/oauth", tags=["integrations"])
settings = get_settings()

logger = logging.getLogger("code9.integrations.amocrm")

# Redis state key. TTL 10 минут — amoCRM рекомендует ≤15.
_OAUTH_STATE_PREFIX = "oauth_state:amocrm:"
_OAUTH_STATE_TTL_SECONDS = 600

# Webhook-pairing TTL — время жизни ожидания credentials от amoCRM
# для external_button. 10 минут покрывает и медленный клик клиента, и
# редкие сетевые задержки.
_EXTERNAL_PAIRING_PREFIX = "oauth_pair:amocrm:"
_EXTERNAL_PAIRING_TTL_SECONDS = 600

# Секреты, которые логгер МОЖЕТ случайно получить через extra={"key": ...}.
# На уровне маскера они так же режутся, но явный allow-list здесь
# помогает читающему код понять, что мы НЕ логируем.
_SENSITIVE_LOG_KEYS = frozenset(
    {"code", "access_token", "refresh_token", "client_secret"}
)


def _auth_mode() -> str:
    """Нормализованный режим (static_client | external_button)."""
    return (settings.amocrm_auth_mode or "static_client").lower().strip()


async def _ensure_member(
    session: AsyncSession, user: User, workspace_id: uuid.UUID
) -> Workspace:
    """Проверяет, что user — owner/admin workspace, иначе 403/404."""
    from sqlalchemy import select

    ws = (
        await session.execute(select(Workspace).where(Workspace.id == workspace_id))
    ).scalar_one_or_none()
    if not ws:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Workspace not found"}},
        )
    m = (
        await session.execute(
            select(WorkspaceMember)
            .where(WorkspaceMember.workspace_id == workspace_id)
            .where(WorkspaceMember.user_id == user.id)
        )
    ).scalar_one_or_none()
    if not m or m.role not in {"owner", "admin"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "forbidden", "message": "Not an owner/admin"}},
        )
    return ws


def _redirect_uri() -> str:
    """
    redirect_uri должен совпадать точно с зарегистрированным в amoCRM.

    Приоритет:
      1. AMOCRM_REDIRECT_URI из env (если задан).
      2. BASE_URL + /api/v1/integrations/amocrm/oauth/callback (fallback для dev).
    """
    if settings.amocrm_redirect_uri:
        return settings.amocrm_redirect_uri
    return f"{settings.base_url}/api/v1/integrations/amocrm/oauth/callback"


@router.get("/start")
async def oauth_start(
    workspace_id: uuid.UUID,
    connection_name: str | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Any:
    """
    Начало OAuth для amoCRM.

    MOCK: сразу создаёт active подключение + enqueue bootstrap_tenant_schema.
    REAL: создаёт pending подключение, формирует authorize_url и кладёт state
    в Redis. BE отдаёт JSON `{authorize_url, state, connection_id}`; фронт
    сам делает `window.location.assign(authorize_url)`.
    """
    ws = await _ensure_member(session, user, workspace_id)

    if settings.mock_crm_mode:
        shortid = secrets.token_hex(4)
        conn = CrmConnection(
            workspace_id=ws.id,
            name=connection_name or "amoCRM (mock)",
            provider="amocrm",
            status="active",
            external_account_id=f"mock-{shortid}",
            external_domain="mock-amo.local",
            tenant_schema=None,
            metadata_json={"mock": True, "source": "oauth_start"},
        )
        session.add(conn)
        await session.flush()

        bootstrap_rq_id = enqueue(
            "bootstrap_tenant_schema", {"connection_id": str(conn.id)}
        )
        session.add(
            Job(
                workspace_id=ws.id,
                crm_connection_id=conn.id,
                kind="bootstrap_tenant_schema",
                queue=queue_for_kind("bootstrap_tenant_schema"),
                status="queued",
                payload={"connection_id": str(conn.id)},
                rq_job_id=bootstrap_rq_id,
            )
        )

        # Mock: цепочка bootstrap → pull_amocrm_core (в mock-режиме
        # pull делегирует в trial_export → audit, полная UX-параллель с prod).
        pull_payload = {"connection_id": str(conn.id), "first_pull": True}
        pull_rq_id = enqueue(
            "pull_amocrm_core", pull_payload, depends_on=bootstrap_rq_id
        )
        session.add(
            Job(
                workspace_id=ws.id,
                crm_connection_id=conn.id,
                kind="pull_amocrm_core",
                queue=queue_for_kind("pull_amocrm_core"),
                status="queued",
                payload=pull_payload,
                rq_job_id=pull_rq_id,
            )
        )
        await session.commit()

        return {
            "mock": True,
            "connection_id": str(conn.id),
            "redirect_url": f"/app/connections/{conn.id}",
        }

    # ---- REAL MODE (Phase 2A) -----------------------------------------------

    auth_mode = _auth_mode()

    try:
        from crm_connectors.amocrm import AmoCrmConnector  # type: ignore  # noqa: F401
    except Exception as exc:
        # Этот случай — configuration error на стороне деплоя (PYTHONPATH).
        # 501 — потому что в prod валидатор уже требует установленный пакет.
        logger.error(
            "amocrm_connector_import_failed",
            extra={"error_type": type(exc).__name__},
        )
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail={
                "error": {
                    "code": "configuration_error",
                    "message": "amoCRM connector not available on server.",
                }
            },
        )

    if auth_mode == "static_client" and not settings.amocrm_client_id:
        # В проде check_prod_secrets уже отловил бы это, но dev без env
        # даёт 501 вместо stacktrace'а.
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail={
                "error": {
                    "code": "configuration_error",
                    "message": "AMOCRM_CLIENT_ID не задан (static_client).",
                }
            },
        )
    if auth_mode == "external_button" and not settings.effective_amocrm_secrets_uri:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail={
                "error": {
                    "code": "configuration_error",
                    "message": (
                        "AMOCRM_SECRETS_URI не задан (external_button). "
                        "Legacy alias AMOCRM_EXTERNAL_WEBHOOK_URL тоже пуст."
                    ),
                }
            },
        )

    # 1) Создаём pending CrmConnection. Токенов ещё нет — они появятся в callback.
    conn = CrmConnection(
        workspace_id=ws.id,
        name=connection_name or "amoCRM",
        provider="amocrm",
        status="pending",
        tenant_schema=None,
        amocrm_auth_mode=auth_mode,
        metadata_json={
            "source": "oauth_start",
            "mock": False,
            "amocrm_auth_mode": auth_mode,
        },
    )
    session.add(conn)
    await session.flush()

    # 2) Генерируем state и кладём в Redis связку с workspace/connection/user.
    state = secrets.token_urlsafe(24)
    state_payload = {
        "workspace_id": str(ws.id),
        "connection_id": str(conn.id),
        "user_id": str(user.id),
        "auth_mode": auth_mode,
    }
    redis = get_redis()
    await redis.setex(
        f"{_OAUTH_STATE_PREFIX}{state}",
        _OAUTH_STATE_TTL_SECONDS,
        json.dumps(state_payload),
    )

    # 3a) static_client — собираем authorize URL прямо сейчас.
    if auth_mode == "static_client":
        from crm_connectors.amocrm import AmoCrmConnector  # type: ignore

        connector = AmoCrmConnector(
            client_id=settings.amocrm_client_id,
            client_secret=settings.amocrm_client_secret,
        )
        try:
            authorize_url = connector.oauth_authorize_url(
                state=state, redirect_uri=_redirect_uri()
            )
        except Exception as exc:
            logger.error(
                "amocrm_oauth_start_failed",
                extra={"error_type": type(exc).__name__},
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": {"code": "internal", "message": "OAuth start failed"}
                },
            )

        await session.commit()
        logger.info(
            "amocrm_oauth_started",
            extra={
                "workspace_id": str(ws.id),
                "connection_id": str(conn.id),
                "auth_mode": auth_mode,
            },
        )
        return {
            "mock": False,
            "auth_mode": auth_mode,
            "connection_id": str(conn.id),
            "authorize_url": authorize_url,
            "state": state,
        }

    # 3b) external_button — пара (state ↔ connection_id) уже в Redis;
    # фронт получит конфиг кнопки через GET /button-config и
    # отрендерит официальный widget amoCRM. После клика клиента
    # amoCRM пришлёт нам webhook на /external/secrets (primary) или
    # на /external/credentials (legacy alias), а юзера переадресует
    # на наш /callback?code=…&state=…&referer=….
    await session.commit()
    logger.info(
        "amocrm_oauth_started",
        extra={
            "workspace_id": str(ws.id),
            "connection_id": str(conn.id),
            "auth_mode": auth_mode,
        },
    )
    return {
        "mock": False,
        "auth_mode": auth_mode,
        "connection_id": str(conn.id),
        "state": state,
        # authorize_url здесь null — фронт ждёт webhook через polling
        # либо использует embedded button (см. /button-config).
        "authorize_url": None,
        "redirect_uri": _redirect_uri(),
    }


def _ui_redirect(path: str) -> RedirectResponse:
    """
    Редирект на фронт (Next.js). `settings.base_url` — API-хост; для фронт-URL
    берём ``allowed_origins_list`` первый элемент (там прописаны frontend-origin'ы).
    """
    origins = settings.allowed_origins_list
    frontend = origins[0] if origins else settings.base_url
    return RedirectResponse(url=f"{frontend}{path}")


@router.get("/button-config")
async def button_config() -> dict[str, Any]:
    """
    Возвращает фронту публичный конфиг для рендера UI-кнопки amoCRM.

    Во всех режимах отдаём `auth_mode` + `redirect_uri`. В external_button
    дополнительно:
      * `secrets_uri` — primary (соответствует amoCRM data-secrets_uri).
      * `webhook_url` — legacy alias, дублирует `secrets_uri` (остаётся для
        фронтов, которые ещё не мигрировали на новое имя). Новый код
        должен читать `secrets_uri`.
      * `button` — публичная метаинформация (name/description/logo/
        scopes/title) для <script class="amocrm_oauth"> data-*.
      * `wait_seconds` — сколько callback ждёт webhook.

    Эндпоинт публичный для авторизованного пользователя — никаких
    секретов не отдаёт (client_secret тут не фигурирует вообще,
    client_id для external_button его не имеет на этом этапе).
    """
    auth_mode = _auth_mode()
    resp: dict[str, Any] = {
        "mock": settings.mock_crm_mode,
        "auth_mode": auth_mode,
        "redirect_uri": _redirect_uri() if not settings.mock_crm_mode else None,
    }
    if auth_mode == "external_button" and not settings.mock_crm_mode:
        effective_uri = settings.effective_amocrm_secrets_uri
        # Primary имя по v2. `webhook_url` оставляем для legacy-фронтов —
        # оно дублирует значение, никаких отдельных секретов не несёт.
        resp["secrets_uri"] = effective_uri
        resp["webhook_url"] = effective_uri
        resp["wait_seconds"] = settings.amocrm_external_wait_seconds
        # Публичная метаинформация для встраивания в официальный
        # <script class="amocrm_oauth"> — без секретов.
        resp["button"] = {
            "name": settings.amocrm_button_name or None,
            "description": settings.amocrm_button_description or None,
            "logo": settings.amocrm_button_logo or None,
            "scopes": settings.amocrm_button_scopes or None,
            "title": settings.amocrm_button_title or None,
        }
    if auth_mode == "static_client" and not settings.mock_crm_mode:
        # client_id — публичное значение, фронт рендерит authorize-URL
        # сразу либо вызывает /oauth/start.
        resp["client_id"] = settings.amocrm_client_id or None
    return resp


@router.get("/callback")
async def oauth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    referer: str | None = None,
    error: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> Any:
    """
    OAuth callback.

    amoCRM query-параметры:
      * ``code``    — authorization_code (для exchange_code).
      * ``state``   — то, что мы положили в authorize_url.
      * ``referer`` — ``account.amocrm.ru`` (без ``https://``). Мы вытаскиваем
        отсюда ``subdomain`` → передаём в AmoCrmConnector.
      * ``error``   — если юзер отказал / недоступно (редкий кейс).

    MOCK: просто редиректим (в mock-режиме start уже всё сделал).
    REAL: полная цепочка.
    """
    if settings.mock_crm_mode:
        return _ui_redirect("/app/connections?flash=mock_oauth_ok")

    # ---- REAL MODE ----------------------------------------------------------

    if error:
        # Пользователь отказал / amoCRM вернул ошибку на authorize-шаге.
        logger.info("amocrm_oauth_user_declined", extra={"error": error})
        return _ui_redirect("/app/connections?flash=amocrm_cancelled")

    if not code or not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "validation_error", "message": "Missing code/state"}},
        )

    # 1) Верифицируем state + забираем payload из Redis.
    redis = get_redis()
    raw_state = await redis.get(f"{_OAUTH_STATE_PREFIX}{state}")
    if not raw_state:
        # state просрочен, подменён или уже использован.
        logger.warning("amocrm_oauth_state_miss", extra={"state_prefix": state[:8]})
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "invalid_state",
                    "message": "State expired or invalid. Начните OAuth заново.",
                }
            },
        )
    # Сразу удаляем — защита от replay.
    await redis.delete(f"{_OAUTH_STATE_PREFIX}{state}")

    try:
        state_payload = json.loads(raw_state)
        workspace_id = uuid.UUID(state_payload["workspace_id"])
        connection_id = uuid.UUID(state_payload["connection_id"])
        # auth_mode в state может отсутствовать (старые pending'и) —
        # фолбэк на текущую global-настройку.
        state_auth_mode = (
            state_payload.get("auth_mode") or _auth_mode()
        ).lower().strip()
    except (KeyError, ValueError, json.JSONDecodeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "invalid_state", "message": "State payload corrupt"}},
        )

    # 2) Достаём pending connection.
    from sqlalchemy import select

    conn = (
        await session.execute(
            select(CrmConnection).where(CrmConnection.id == connection_id)
        )
    ).scalar_one_or_none()
    if not conn or conn.workspace_id != workspace_id or conn.provider != "amocrm":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Connection not found"}},
        )

    # 3) Достаём subdomain из referer (amoCRM присылает его как `account.amocrm.ru`).
    subdomain = _extract_subdomain(referer)
    if not subdomain:
        logger.warning(
            "amocrm_oauth_no_subdomain",
            extra={"referer": referer, "connection_id": str(conn.id)},
        )
        _fail_connection(conn, "referer missing — amoCRM не прислал account subdomain")
        await session.commit()
        return _ui_redirect(f"/app/connections/{conn.id}?flash=amocrm_bad_referer")

    # 3.5) Резолвим OAuth-credentials по режиму.
    #
    # static_client → берём из settings (один на всех клиентов).
    # external_button → ждём webhook'а от amoCRM до 5с (backoff 0.5с).
    #                   Если в БД уже лежат — берём сразу.
    if state_auth_mode == "external_button":
        client_id_resolved, client_secret_resolved = await _await_external_credentials(
            session=session,
            conn=conn,
            wait_seconds=settings.amocrm_external_wait_seconds,
        )
        if not client_id_resolved or not client_secret_resolved:
            _fail_connection(
                conn,
                "amoCRM не прислал client_id/secret в окно ожидания "
                f"({settings.amocrm_external_wait_seconds}s)",
            )
            await session.commit()
            logger.warning(
                "amocrm_oauth_credentials_missing",
                extra={
                    "connection_id": str(conn.id),
                    "wait_seconds": settings.amocrm_external_wait_seconds,
                },
            )
            return _ui_redirect(
                f"/app/connections/{conn.id}?flash=amocrm_credentials_missing"
            )
    else:
        client_id_resolved = settings.amocrm_client_id
        client_secret_resolved = settings.amocrm_client_secret

    # 4) exchange_code — блокирующий httpx-call. FastAPI выполняет sync-функции
    # в threadpool'е; для 1 запроса на подключение это ОК.
    from crm_connectors.amocrm import AmoCrmConnector  # type: ignore
    from crm_connectors.exceptions import (  # type: ignore
        InvalidGrant,
        ProviderError,
        RateLimited,
        TokenExpired,
    )

    connector = AmoCrmConnector(
        client_id=client_id_resolved,
        client_secret=client_secret_resolved,
        subdomain=subdomain,
    )

    try:
        tokens = connector.exchange_code(code=code, redirect_uri=_redirect_uri())
    except InvalidGrant:
        logger.warning("amocrm_exchange_invalid_grant", extra={"connection_id": str(conn.id)})
        _fail_connection(conn, "amoCRM отклонил authorization_code (invalid_grant)")
        await session.commit()
        return _ui_redirect(f"/app/connections/{conn.id}?flash=amocrm_invalid_grant")
    except (ProviderError, TokenExpired, RateLimited) as exc:
        logger.error(
            "amocrm_exchange_failed",
            extra={
                "connection_id": str(conn.id),
                "error_type": type(exc).__name__,
            },
        )
        _fail_connection(conn, f"amoCRM exchange failed: {type(exc).__name__}")
        await session.commit()
        return _ui_redirect(f"/app/connections/{conn.id}?flash=amocrm_exchange_failed")

    # 5) fetch_account — нужен external_account_id + domain.
    try:
        account = connector.fetch_account(tokens.access_token)
    except Exception as exc:
        # Не блокируем подключение: токены есть → бэкграундный pull доберёт
        # account.  Но пишем предупреждение в last_error.
        logger.warning(
            "amocrm_fetch_account_failed",
            extra={
                "connection_id": str(conn.id),
                "error_type": type(exc).__name__,
            },
        )
        account = {}

    # 6) Шифруем токены ДО записи в БД.
    try:
        access_enc = encrypt_token(tokens.access_token)
        refresh_enc = encrypt_token(tokens.refresh_token)
    except Exception as exc:
        logger.error(
            "amocrm_token_encrypt_failed",
            extra={"connection_id": str(conn.id), "error_type": type(exc).__name__},
        )
        _fail_connection(conn, "token encryption failed — проверьте FERNET_KEY")
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": {"code": "internal", "message": "Token storage failed"}},
        )

    # 7) Обновляем CrmConnection.
    account_id = account.get("id") if isinstance(account, dict) else None
    account_subdomain = account.get("subdomain") if isinstance(account, dict) else None
    conn.access_token_encrypted = access_enc
    conn.refresh_token_encrypted = refresh_enc
    conn.token_expires_at = tokens.expires_at
    conn.external_account_id = str(account_id) if account_id is not None else None
    conn.external_domain = (
        f"{account_subdomain}.amocrm.ru" if account_subdomain else f"{subdomain}.amocrm.ru"
    )
    conn.status = "active"
    conn.last_error = None
    # Сохраняем ВАЖНЫЕ поля account в metadata, но НЕ токены и НЕ raw OAuth-ответ.
    safe_meta = {
        "mock": False,
        "source": "oauth_callback",
        "amocrm_auth_mode": state_auth_mode,
        "amo_account": {
            "id": account.get("id") if isinstance(account, dict) else None,
            "name": account.get("name") if isinstance(account, dict) else None,
            "subdomain": account.get("subdomain") if isinstance(account, dict) else subdomain,
            "country": account.get("country") if isinstance(account, dict) else None,
            "currency": account.get("currency") if isinstance(account, dict) else None,
        },
    }
    # mypy-friendly merge — metadata_json может уже что-то содержать
    existing_meta = dict(conn.metadata_json or {})
    existing_meta.update(safe_meta)
    conn.metadata_json = existing_meta

    # 8) Enqueue bootstrap_tenant_schema → pull_amocrm_core (dependency chain).
    #    Phase 2A: после bootstrap сразу стартует first-pull 4 ядер.
    #    pull_amocrm_core сам enqueue-ит audit после успешного завершения.
    bootstrap_rq_id = enqueue(
        "bootstrap_tenant_schema", {"connection_id": str(conn.id)}
    )
    session.add(
        Job(
            workspace_id=workspace_id,
            crm_connection_id=conn.id,
            kind="bootstrap_tenant_schema",
            queue=queue_for_kind("bootstrap_tenant_schema"),
            status="queued",
            payload={"connection_id": str(conn.id)},
            rq_job_id=bootstrap_rq_id,
        )
    )

    pull_payload = {"connection_id": str(conn.id), "first_pull": True}
    pull_rq_id = enqueue(
        "pull_amocrm_core", pull_payload, depends_on=bootstrap_rq_id
    )
    session.add(
        Job(
            workspace_id=workspace_id,
            crm_connection_id=conn.id,
            kind="pull_amocrm_core",
            queue=queue_for_kind("pull_amocrm_core"),
            status="queued",
            payload=pull_payload,
            rq_job_id=pull_rq_id,
        )
    )

    await session.commit()
    logger.info(
        "amocrm_oauth_completed",
        extra={
            "connection_id": str(conn.id),
            "workspace_id": str(workspace_id),
            "amo_account_id": str(account_id) if account_id else None,
        },
    )
    return _ui_redirect(f"/app/connections/{conn.id}?flash=amocrm_connected")


def _fail_connection(conn: CrmConnection, message: str) -> None:
    """Перевести подключение в error с короткой формулировкой."""
    conn.status = "error"
    conn.last_error = message[:500]  # хедрум в text-поле


def _extract_subdomain(referer: str | None) -> str | None:
    """
    amoCRM callback referer может быть:
      * 'account.amocrm.ru'
      * 'https://account.amocrm.ru'
      * 'https://account.amocrm.ru/path'

    Нам нужна только первая часть до первой точки, и это именно account slug.
    """
    if not referer:
        return None
    raw = referer.strip()
    # Срезаем схему если есть
    for prefix in ("https://", "http://"):
        if raw.startswith(prefix):
            raw = raw[len(prefix):]
            break
    # Срезаем путь
    raw = raw.split("/", 1)[0]
    # account.amocrm.ru → account
    if "." not in raw:
        return None
    slug = raw.split(".", 1)[0].strip().lower()
    # простая sanity-проверка
    if not slug or not slug.replace("-", "").isalnum():
        return None
    return slug


# ============================================================================
# external_button (#44.6) — webhook + helpers
# ============================================================================


async def _await_external_credentials(
    *,
    session: AsyncSession,
    conn: CrmConnection,
    wait_seconds: float,
    poll_interval: float = 0.5,
) -> tuple[str | None, str | None]:
    """
    Ждём, пока webhook-handler не сохранит amocrm_client_id/secret в БД.

    В external_button режиме user и amoCRM-webhook приходят почти
    одновременно: user — на /oauth/callback?code=…, webhook — на
    /external/credentials. Из-за разной сетевой задержки callback
    может оказаться раньше. Здесь мы:

      1) проверяем текущее состояние conn;
      2) если secret пуст — ждём `poll_interval`с и рефрешим из БД;
      3) повторяем, пока не набежит `wait_seconds`.

    Возвращаем (client_id, client_secret_plaintext) либо (None, None)
    на таймауте.
    """
    from sqlalchemy import select

    if conn.amocrm_client_id and conn.amocrm_client_secret_encrypted:
        return conn.amocrm_client_id, decrypt_token(conn.amocrm_client_secret_encrypted)

    deadline_iterations = max(1, int(wait_seconds / poll_interval))
    for _ in range(deadline_iterations):
        await asyncio.sleep(poll_interval)
        # Обязательно обновляем из БД — другой request (webhook) только
        # что положил туда секрет. session.refresh перечитывает те же
        # поля, что уже в identity map.
        fresh = (
            await session.execute(
                select(CrmConnection).where(CrmConnection.id == conn.id)
            )
        ).scalar_one_or_none()
        if fresh is None:
            return None, None
        if fresh.amocrm_client_id and fresh.amocrm_client_secret_encrypted:
            # Обновляем текущий объект — callback продолжит работать с ним.
            conn.amocrm_client_id = fresh.amocrm_client_id
            conn.amocrm_client_secret_encrypted = fresh.amocrm_client_secret_encrypted
            conn.amocrm_external_integration_id = fresh.amocrm_external_integration_id
            conn.amocrm_credentials_received_at = fresh.amocrm_credentials_received_at
            try:
                return fresh.amocrm_client_id, decrypt_token(
                    fresh.amocrm_client_secret_encrypted
                )
            except Exception as exc:
                logger.error(
                    "amocrm_external_secret_decrypt_failed",
                    extra={
                        "connection_id": str(conn.id),
                        "error_type": type(exc).__name__,
                    },
                )
                return None, None
    return None, None


