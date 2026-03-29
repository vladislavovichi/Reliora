from __future__ import annotations

from dataclasses import dataclass

from aiogram import Bot, Dispatcher
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from bot.dispatcher import build_bot, build_dispatcher
from infrastructure.config import Settings
from infrastructure.db.session import build_engine, build_session_factory, dispose_engine
from infrastructure.redis.client import build_redis_client, close_redis_client, ping_redis_client


@dataclass(slots=True)
class AppRuntime:
    settings: Settings
    db_engine: AsyncEngine
    db_session_factory: async_sessionmaker[AsyncSession]
    redis: Redis
    dispatcher: Dispatcher | None = None
    bot: Bot | None = None


async def build_runtime(settings: Settings) -> AppRuntime:
    db_engine = build_engine(settings.database)
    db_session_factory = build_session_factory(db_engine)
    redis = build_redis_client(settings.redis)
    bot: Bot | None = None

    try:
        await ping_redis_client(redis)

        dispatcher: Dispatcher | None = None
        if settings.bot.token:
            bot = build_bot(settings.bot)
            dispatcher = build_dispatcher(
                settings=settings,
                db_session_factory=db_session_factory,
                redis=redis,
            )

        return AppRuntime(
            settings=settings,
            db_engine=db_engine,
            db_session_factory=db_session_factory,
            redis=redis,
            dispatcher=dispatcher,
            bot=bot,
        )
    except Exception:
        if bot is not None:
            await bot.session.close()
        await close_redis_client(redis)
        await dispose_engine(db_engine)
        raise


async def close_runtime(runtime: AppRuntime) -> None:
    if runtime.bot is not None:
        await runtime.bot.session.close()

    await close_redis_client(runtime.redis)
    await dispose_engine(runtime.db_engine)
