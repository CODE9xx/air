"""
Code9 Analytics — точка входа FastAPI.

Wave 2: подключены роутеры auth/workspaces/crm/dashboards/billing/jobs/ai/admin/notifications.
"""
from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.admin.router import router as admin_router
from app.ai.router import router as ai_router
from app.auth.router import router as auth_router
from app.billing.router import router as billing_router
from app.core.log_mask import install_log_masker
from app.core.settings import get_settings
from app.crm.external_router import router as crm_external_router
from app.crm.oauth_router import router as crm_oauth_router
from app.crm.router import router as crm_router
from app.crm.router import ws_crm_router
from app.dashboards.router import router as dashboards_router
from app.jobs.router import router as jobs_router
from app.notifications.router import router as notifications_router
from app.users.router import router as users_router
from app.workspaces.router import router as workspaces_router

settings = get_settings()
install_log_masker(level=logging.INFO)

app = FastAPI(
    title="Code9 Analytics API",
    version="0.2.0",
    description="Backend для подключения amoCRM/Kommo/Bitrix24 и AI-аналитики.",
)


# ---------- CORS ----------

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Request-ID middleware ----------

class RequestIdMiddleware(BaseHTTPMiddleware):
    """Добавляет X-Request-Id в каждый ответ."""

    async def dispatch(self, request: Request, call_next):
        req_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = req_id
        response = await call_next(request)
        response.headers["X-Request-Id"] = req_id
        return response


app.add_middleware(RequestIdMiddleware)


# ---------- Exception handlers (единый формат ошибок) ----------

def _error_response(code: str, message: str, http_status: int, field_errors: dict | None = None) -> JSONResponse:
    body: dict = {"error": {"code": code, "message": message}}
    if field_errors:
        body["error"]["field_errors"] = field_errors
    return JSONResponse(status_code=http_status, content=body)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """HTTPException возвращаем как есть (если detail уже в формате {error:...})."""
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail, headers=exc.headers)
    code_map = {
        400: "validation_error",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        429: "rate_limited",
    }
    code = code_map.get(exc.status_code, "error")
    return _error_response(code, str(exc.detail), exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    field_errors: dict[str, str] = {}
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", []) if p != "body")
        field_errors[loc or "body"] = err.get("msg", "invalid")
    return _error_response(
        "validation_error", "Request validation failed", 422, field_errors
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logging.getLogger("code9").exception("Unhandled exception: %s", exc)
    return _error_response("internal_error", "Internal server error", 500)


# ---------- Meta endpoints (без /api/v1) ----------

@app.get("/", tags=["meta"])
async def root() -> dict[str, str]:
    return {"service": "code9-api", "env": settings.app_env, "version": app.version}


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/health", tags=["meta"])
async def health_deep() -> dict[str, str]:
    """Health deep — проверяет db + redis (мягко, не падает)."""
    db_ok = "unknown"
    redis_ok = "unknown"
    try:
        from sqlalchemy import text

        from app.core.db import AsyncSessionLocal

        async with AsyncSessionLocal() as s:
            await s.execute(text("SELECT 1"))
            db_ok = "ok"
    except Exception:
        db_ok = "fail"
    try:
        from app.core.redis import get_redis

        r = get_redis()
        await r.ping()
        redis_ok = "ok"
    except Exception:
        redis_ok = "fail"
    return {"status": "ok", "db": db_ok, "redis": redis_ok}


# ---------- Подключение всех роутеров под /api/v1 ----------

API_PREFIX = "/api/v1"

app.include_router(auth_router, prefix=API_PREFIX)
app.include_router(users_router, prefix=API_PREFIX)
app.include_router(workspaces_router, prefix=API_PREFIX)
app.include_router(notifications_router, prefix=API_PREFIX)
app.include_router(crm_router, prefix=API_PREFIX)
app.include_router(ws_crm_router, prefix=API_PREFIX)  # /workspaces/{ws}/crm/* (#52.4)
app.include_router(crm_oauth_router, prefix=API_PREFIX)
app.include_router(crm_external_router, prefix=API_PREFIX)
app.include_router(billing_router, prefix=API_PREFIX)
app.include_router(jobs_router, prefix=API_PREFIX)
app.include_router(dashboards_router, prefix=API_PREFIX)
app.include_router(ai_router, prefix=API_PREFIX)
app.include_router(admin_router, prefix=API_PREFIX)
