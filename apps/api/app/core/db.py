"""
Async SQLAlchemy engine + session dependency.

Все роутеры получают сессию через `Depends(get_session)`.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.settings import get_settings

_settings = get_settings()

# Создаём engine единожды. echo=False в prod — поменяем через env при необходимости.
engine = create_async_engine(
    _settings.database_url,
    pool_size=10,
    max_overflow=10,
    pool_pre_ping=True,
    future=True,
)

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — выдаёт AsyncSession с автоматическим rollback при исключении."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def exec_raw(sql: str, params: dict[str, Any] | None = None) -> Any:
    """Выполнить сырой SQL (нужно для SET search_path и т.п.)."""
    from sqlalchemy import text

    async with AsyncSessionLocal() as session:
        result = await session.execute(text(sql), params or {})
        await session.commit()
        return result
