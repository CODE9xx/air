"""
Rate-limiter на Redis (sliding window через INCR + PEXPIRE).

Используется как FastAPI dependency для конкретных endpoints.
"""
from __future__ import annotations

import time
from typing import Callable

from fastapi import HTTPException, Request, status

from app.core.redis import get_redis


async def _incr_window(key: str, window_seconds: int, limit: int) -> tuple[bool, int]:
    """
    Инкрементируем счётчик в бакете шириной `window_seconds`.

    Возвращает (allowed, retry_after_seconds).
    """
    r = get_redis()
    bucket = int(time.time() // window_seconds)
    redis_key = f"rl:{key}:{bucket}"
    current = await r.incr(redis_key)
    if current == 1:
        await r.expire(redis_key, window_seconds + 1)
    allowed = current <= limit
    retry_after = window_seconds - (int(time.time()) % window_seconds)
    return allowed, retry_after


def rate_limit(
    scope: str,
    limit: int,
    window_seconds: int,
    key_builder: Callable[[Request], str] | None = None,
):
    """
    Вернёт FastAPI dependency. `key_builder(request) -> идентификатор ключа`.

    По умолчанию — client IP.
    """

    def _default_key(req: Request) -> str:
        return req.client.host if req.client else "unknown"

    builder = key_builder or _default_key

    async def dep(request: Request) -> None:
        ident = builder(request)
        allowed, retry_after = await _incr_window(
            f"{scope}:{ident}", window_seconds, limit
        )
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": {
                        "code": "rate_limited",
                        "message": f"Too many requests in scope '{scope}'.",
                    }
                },
                headers={"Retry-After": str(retry_after)},
            )

    return dep


async def check_rate(scope: str, ident: str, limit: int, window_seconds: int) -> None:
    """
    Инлайн-проверка лимита (используется, когда ключ зависит от body, а не только от request).

    Кидает HTTPException 429 при превышении.
    """
    allowed, retry_after = await _incr_window(
        f"{scope}:{ident}", window_seconds, limit
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": {
                    "code": "rate_limited",
                    "message": f"Too many requests in scope '{scope}'.",
                }
            },
            headers={"Retry-After": str(retry_after)},
        )


def client_ip(request: Request) -> str:
    """Выдаёт IP из X-Forwarded-For или request.client."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
