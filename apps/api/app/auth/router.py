"""
Auth endpoints — register, login, refresh, logout, password-reset, verify-email, me.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.schemas import (
    LoginRequest,
    LoginResponse,
    MeResponse,
    PasswordChangeRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    RefreshResponse,
    RegisterRequest,
    RegisterResponse,
    UserBrief,
    VerifyEmailConfirmRequest,
    VerifyEmailWithEmailRequest,
)
from app.core.db import get_session
from app.core.email import send_verification_code
from app.core.rate_limit import check_rate, client_ip, rate_limit
from app.core.security import (
    build_session_cookie,
    create_access_token,
    generate_email_code,
    generate_refresh_token,
    hash_secret,
    split_session_cookie,
    verify_secret,
)
from app.core.settings import get_settings
from app.db.models import (
    BillingAccount,
    EmailVerificationCode,
    User,
    UserSession,
    Workspace,
    WorkspaceMember,
)

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


def _slugify(s: str) -> str:
    """Минимальный slugify для auto-named workspace."""
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "ws"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _set_refresh_cookie(response: Response, value: str) -> None:
    """Ставит httpOnly secure cookie с refresh-сессией."""
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=value,
        max_age=settings.refresh_token_ttl_seconds,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        path="/api/v1/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path="/api/v1/auth",
    )


# -------------------- POST /auth/register --------------------

@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("auth_register", limit=3, window_seconds=60, key_builder=client_ip))],
)
async def register(
    body: RegisterRequest,
    session: AsyncSession = Depends(get_session),
) -> RegisterResponse:
    # Проверяем дубликат email.
    existing = await session.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "conflict", "message": "Email already registered"}},
        )

    user = User(
        email=body.email,
        password_hash=hash_secret(body.password),
        locale=body.locale,
        status="active",
    )
    session.add(user)
    await session.flush()  # чтобы получить user.id

    # Auto-name workspace + slug.
    base_slug = _slugify(body.email.split("@")[0])
    slug = f"{base_slug}-{str(user.id)[:8]}"
    workspace = Workspace(
        name=f"{body.email}'s workspace",
        slug=slug,
        owner_user_id=user.id,
        locale=body.locale,
        status="active",
    )
    session.add(workspace)
    await session.flush()

    member = WorkspaceMember(
        workspace_id=workspace.id,
        user_id=user.id,
        role="owner",
        accepted_at=_now(),
    )
    session.add(member)

    # Billing-аккаунт сразу.
    billing = BillingAccount(workspace_id=workspace.id)
    session.add(billing)

    # Email-код.
    code = generate_email_code()
    evc = EmailVerificationCode(
        user_id=user.id,
        purpose="email_verify",
        code_hash=hash_secret(code),
        expires_at=_now() + timedelta(minutes=15),
    )
    session.add(evc)

    await session.commit()

    # Шлём email (DEV — в логи).
    send_verification_code(body.email, code, "email_verify")

    return RegisterResponse(
        user_id=str(user.id),
        workspace_id=str(workspace.id),
        email_verification_required=True,
    )


# -------------------- POST /auth/login --------------------

@router.post(
    "/login",
    response_model=LoginResponse,
    dependencies=[Depends(rate_limit("auth_login_ip", limit=5, window_seconds=60, key_builder=client_ip))],
)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> LoginResponse:
    # Дополнительный лимит по email (10/min).
    await check_rate("auth_login_email", body.email.lower(), limit=10, window_seconds=60)

    user = (
        await session.execute(select(User).where(User.email == body.email))
    ).scalar_one_or_none()

    if not user or not verify_secret(user.password_hash, body.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "invalid_credentials", "message": "Invalid email or password"}},
        )

    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "forbidden", "message": "User is locked or deleted"}},
        )

    # email_verified — мягкая проверка: возвращаем 403 если нет.
    if user.email_verified_at is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "email_not_verified", "message": "Email not verified"}},
        )

    # Создаём refresh-session.
    opaque = generate_refresh_token()
    session_row = UserSession(
        user_id=user.id,
        refresh_token_hash=hash_secret(opaque),
        user_agent=request.headers.get("user-agent"),
        ip=client_ip(request),
        expires_at=_now() + timedelta(seconds=settings.refresh_token_ttl_seconds),
    )
    session.add(session_row)
    user.last_login_at = _now()
    await session.commit()

    _set_refresh_cookie(response, build_session_cookie(str(session_row.id), opaque))

    access, ttl = create_access_token(str(user.id), scope="user")
    return LoginResponse(
        access_token=access,
        access_token_expires_in=ttl,
        user=UserBrief(
            id=str(user.id),
            email=user.email,
            display_name=user.display_name,
            locale=user.locale,
            email_verified=user.email_verified_at is not None,
        ),
    )


# -------------------- POST /auth/logout --------------------

@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Response:
    cookie_value = request.cookies.get(settings.refresh_cookie_name)
    if cookie_value:
        parsed = split_session_cookie(cookie_value)
        if parsed:
            sid_str, _ = parsed
            try:
                sid = uuid.UUID(sid_str)
                row = (
                    await session.execute(select(UserSession).where(UserSession.id == sid))
                ).scalar_one_or_none()
                if row and row.user_id == user.id and row.revoked_at is None:
                    row.revoked_at = _now()
                    await session.commit()
            except Exception:
                pass

    _clear_refresh_cookie(response)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# -------------------- POST /auth/refresh --------------------

@router.post("/refresh", response_model=RefreshResponse)
async def refresh(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> RefreshResponse:
    cookie_value = request.cookies.get(settings.refresh_cookie_name)
    parsed = split_session_cookie(cookie_value or "")
    if not parsed:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "unauthorized", "message": "Missing refresh cookie"}},
        )
    sid_str, opaque = parsed
    try:
        sid = uuid.UUID(sid_str)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "unauthorized", "message": "Bad session id"}},
        )

    row = (
        await session.execute(select(UserSession).where(UserSession.id == sid))
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "unauthorized", "message": "Session not found"}},
        )

    if row.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "unauthorized", "message": "Session revoked"}},
        )
    if row.expires_at < _now():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "unauthorized", "message": "Session expired"}},
        )
    if not verify_secret(row.refresh_token_hash, opaque):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "unauthorized", "message": "Invalid refresh token"}},
        )

    access, ttl = create_access_token(str(row.user_id), scope="user")
    return RefreshResponse(access_token=access, access_token_expires_in=ttl)


# -------------------- Verify-email --------------------

@router.post(
    "/verify-email/request",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def verify_email_request(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    await check_rate("auth_verify_req", str(user.id), limit=3, window_seconds=600)
    if user.email_verified_at is not None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    code = generate_email_code()
    evc = EmailVerificationCode(
        user_id=user.id,
        purpose="email_verify",
        code_hash=hash_secret(code),
        expires_at=_now() + timedelta(minutes=15),
    )
    session.add(evc)
    await session.commit()
    send_verification_code(user.email, code, "email_verify")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/verify-email/confirm")
async def verify_email_confirm(
    body: VerifyEmailConfirmRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    await check_rate("auth_verify_confirm", str(user.id), limit=10, window_seconds=3600)
    return await _consume_verification_code(
        session=session,
        user=user,
        code=body.code,
        purpose="email_verify",
        on_success={"email_verified": True},
    )


# Альтернативный endpoint без auth — по email + code (бриф попросил так).
@router.post("/verify-email")
async def verify_email_with_email(
    body: VerifyEmailWithEmailRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await check_rate("auth_verify_email", body.email.lower(), limit=10, window_seconds=3600)
    user = (
        await session.execute(select(User).where(User.email == body.email))
    ).scalar_one_or_none()
    if not user:
        # Анти-энумерация: ведём себя как обычная неудача.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "validation_error", "message": "Invalid code"}},
        )
    return await _consume_verification_code(
        session=session,
        user=user,
        code=body.code,
        purpose="email_verify",
        on_success={"email_verified": True},
    )


async def _consume_verification_code(
    session: AsyncSession,
    user: User,
    code: str,
    purpose: str,
    on_success: dict,
) -> dict:
    """Общий хелпер: проверка → инкремент попыток → consumed_at."""
    res = await session.execute(
        select(EmailVerificationCode)
        .where(EmailVerificationCode.user_id == user.id)
        .where(EmailVerificationCode.purpose == purpose)
        .where(EmailVerificationCode.consumed_at.is_(None))
        .order_by(EmailVerificationCode.created_at.desc())
        .limit(1)
    )
    evc = res.scalar_one_or_none()
    if not evc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "code_expired", "message": "No active code"}},
        )

    if evc.expires_at < _now():
        evc.consumed_at = _now()
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "code_expired", "message": "Code expired"}},
        )

    if evc.attempts >= evc.max_attempts:
        evc.consumed_at = _now()
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"error": {"code": "too_many_attempts", "message": "Too many attempts"}},
        )

    evc.attempts += 1
    if not verify_secret(evc.code_hash, code):
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "validation_error", "message": "Invalid code"}},
        )

    evc.consumed_at = _now()
    if purpose == "email_verify":
        user.email_verified_at = _now()

    await session.commit()
    return on_success


# -------------------- Password reset --------------------

@router.post(
    "/password-reset/request",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def password_reset_request(
    body: PasswordResetRequest,
    session: AsyncSession = Depends(get_session),
) -> Response:
    await check_rate("auth_pwd_reset", body.email.lower(), limit=3, window_seconds=600)
    user = (
        await session.execute(select(User).where(User.email == body.email))
    ).scalar_one_or_none()
    # Анти-энумерация: всегда 204.
    if user:
        code = generate_email_code()
        evc = EmailVerificationCode(
            user_id=user.id,
            purpose="password_reset",
            code_hash=hash_secret(code),
            expires_at=_now() + timedelta(minutes=15),
        )
        session.add(evc)
        await session.commit()
        send_verification_code(body.email, code, "password_reset")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/password-reset/confirm")
async def password_reset_confirm(
    body: PasswordResetConfirmRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    user = (
        await session.execute(select(User).where(User.email == body.email))
    ).scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "validation_error", "message": "Invalid code"}},
        )

    # Используем helper, но после — отдельно меняем пароль и revoke сессии.
    res = await session.execute(
        select(EmailVerificationCode)
        .where(EmailVerificationCode.user_id == user.id)
        .where(EmailVerificationCode.purpose == "password_reset")
        .where(EmailVerificationCode.consumed_at.is_(None))
        .order_by(EmailVerificationCode.created_at.desc())
        .limit(1)
    )
    evc = res.scalar_one_or_none()
    if not evc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "code_expired", "message": "No active code"}},
        )
    if evc.expires_at < _now():
        evc.consumed_at = _now()
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "code_expired", "message": "Code expired"}},
        )
    if evc.attempts >= evc.max_attempts:
        evc.consumed_at = _now()
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"error": {"code": "too_many_attempts", "message": "Too many attempts"}},
        )
    evc.attempts += 1
    if not verify_secret(evc.code_hash, body.code):
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "validation_error", "message": "Invalid code"}},
        )

    evc.consumed_at = _now()
    user.password_hash = hash_secret(body.new_password)

    # Revoke ВСЕ refresh-сессии.
    sessions = (
        await session.execute(
            select(UserSession)
            .where(UserSession.user_id == user.id)
            .where(UserSession.revoked_at.is_(None))
        )
    ).scalars().all()
    for s in sessions:
        s.revoked_at = _now()

    await session.commit()
    return {"ok": True}


@router.post("/password/change")
async def password_change(
    body: PasswordChangeRequest,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if not verify_secret(user.password_hash, body.old_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "invalid_credentials", "message": "Wrong password"}},
        )
    user.password_hash = hash_secret(body.new_password)

    # Revoke все сессии кроме текущей.
    cookie = request.cookies.get(settings.refresh_cookie_name)
    parsed = split_session_cookie(cookie or "")
    keep_id: uuid.UUID | None = None
    if parsed:
        try:
            keep_id = uuid.UUID(parsed[0])
        except Exception:
            keep_id = None

    sessions = (
        await session.execute(
            select(UserSession)
            .where(UserSession.user_id == user.id)
            .where(UserSession.revoked_at.is_(None))
        )
    ).scalars().all()
    for s in sessions:
        if keep_id is None or s.id != keep_id:
            s.revoked_at = _now()

    await session.commit()
    return {"ok": True}


# -------------------- GET /auth/me --------------------

@router.get("/me", response_model=MeResponse)
async def me(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MeResponse:
    rows = (
        await session.execute(
            select(WorkspaceMember, Workspace)
            .join(Workspace, Workspace.id == WorkspaceMember.workspace_id)
            .where(WorkspaceMember.user_id == user.id)
            .where(Workspace.status != "deleted")
        )
    ).all()
    workspaces = [
        {"id": str(ws.id), "name": ws.name, "role": m.role}
        for (m, ws) in rows
    ]
    return MeResponse(
        id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        locale=user.locale,
        email_verified=user.email_verified_at is not None,
        two_factor_enabled=user.two_factor_enabled,
        workspaces=workspaces,
    )
