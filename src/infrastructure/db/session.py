from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from infrastructure.config import PostgresConfig


def build_engine(config: PostgresConfig) -> AsyncEngine:
    return create_async_engine(
        config.sqlalchemy_url,
        echo=config.echo,
        pool_pre_ping=True,
    )


def build_session_factory(config: PostgresConfig) -> async_sessionmaker[AsyncSession]:
    engine = build_engine(config)
    return async_sessionmaker(engine, expire_on_commit=False)
