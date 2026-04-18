"""Redis client (async) для rate-limiting, OAuth state, очередей RQ."""
from __future__ import annotations

from functools import lru_cache

import redis.asyncio as aioredis
from redis import Redis as SyncRedis

from app.core.settings import get_settings


@lru_cache(maxsize=1)
def get_redis() -> aioredis.Redis:
    """Async Redis client (для API request cycle)."""
    settings = get_settings()
    return aioredis.from_url(settings.redis_url, decode_responses=True)


@lru_cache(maxsize=1)
def get_sync_redis() -> SyncRedis:
    """Sync Redis client (для RQ enqueue — RQ работает синхронно)."""
    settings = get_settings()
    return SyncRedis.from_url(settings.redis_url, decode_responses=False)
