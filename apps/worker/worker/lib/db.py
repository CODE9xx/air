"""
DB-хелперы для worker'а: sync-сессия (для DDL и Alembic-вызовов) и
async-сессия (для обычной работы с данными).

URL берётся из ``DATABASE_URL``. Async-driver — asyncpg, sync — psycopg2.

SSL-трансляция для sync-контекста
---------------------------------
asyncpg-URL несёт libpq-alias ``ssl=require``; psycopg2 его не понимает
и ждёт полное имя ``sslmode=require``. При конвертации драйвера мы
обязаны также транслировать параметр — иначе managed Postgres (Timeweb)
отобьёт соединение на этапе ``create_engine``. См.
``worker/lib/url_translate.py`` (MIRROR ``apps/api/app/db/url_translate.py``).

Async-URL намеренно остаётся нетронутым: asyncpg использует ``ssl=…``
нативно, менять его не нужно и опасно.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager, contextmanager
from typing import AsyncIterator, Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from .url_translate import asyncpg_to_psycopg2

_async_engine: AsyncEngine | None = None
_sync_engine: Engine | None = None


def _raw_url() -> str:
    return os.getenv("DATABASE_URL", "postgresql+asyncpg://code9:code9@postgres:5432/code9")


def _async_url() -> str:
    """Async-URL для asyncpg. ssl=... НЕ трогаем — asyncpg сам понимает."""
    url = _raw_url()
    if url.startswith("postgresql://") and "+" not in url.split("://", 1)[1]:
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def _sync_url() -> str:
    """Sync-URL (psycopg2): меняем драйвер + ssl → sslmode."""
    return asyncpg_to_psycopg2(_raw_url())


def get_async_engine() -> AsyncEngine:
    global _async_engine
    if _async_engine is None:
        _async_engine = create_async_engine(_async_url(), pool_pre_ping=True)
    return _async_engine


def get_sync_engine() -> Engine:
    global _sync_engine
    if _sync_engine is None:
        _sync_engine = create_engine(_sync_url(), pool_pre_ping=True, future=True)
    return _sync_engine


@asynccontextmanager
async def async_session() -> AsyncIterator[AsyncSession]:
    """Контекст async-сессии c явным commit/rollback."""
    engine = get_async_engine()
    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    session: AsyncSession = maker()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


@contextmanager
def sync_session() -> Iterator[Session]:
    """Sync-сессия для DDL и Alembic-вызовов."""
    engine = get_sync_engine()
    maker = sessionmaker(engine, expire_on_commit=False, future=True)
    session: Session = maker()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
