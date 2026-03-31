from __future__ import annotations

from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis

from bot.dispatcher import build_dispatcher
from infrastructure.redis.fsm import build_fsm_storage


def test_build_fsm_storage_returns_redis_storage() -> None:
    redis = Redis.from_url("redis://localhost:6379/0")
    storage = build_fsm_storage(redis)

    assert isinstance(storage, RedisStorage)
    assert storage.redis is redis


def test_build_dispatcher_uses_provided_storage() -> None:
    redis = Redis.from_url("redis://localhost:6379/0")
    storage = build_fsm_storage(redis)

    dispatcher = build_dispatcher(storage=storage)

    assert dispatcher.storage is storage
