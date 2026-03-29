from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from infrastructure.config import PostgresConfig, get_settings


def build_engine(config: PostgresConfig) -> AsyncEngine:
    return create_async_engine(
        config.sqlalchemy_url,
        echo=config.echo,
        pool_pre_ping=True,
    )


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    settings = get_settings()
    return build_engine(settings.postgres)


@lru_cache(maxsize=1)
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    engine = get_engine()
    return build_session_factory(engine)


@asynccontextmanager
async def session_scope(
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> AsyncIterator[AsyncSession]:
    factory = session_factory or get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine(engine: AsyncEngine | None = None) -> None:
    active_engine = engine or get_engine()
    await active_engine.dispose()

    if engine is None:
        get_session_factory.cache_clear()
        get_engine.cache_clear()
