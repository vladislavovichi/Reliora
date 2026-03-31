from __future__ import annotations

from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis


def build_fsm_storage(redis: Redis) -> RedisStorage:
    return RedisStorage(redis=redis)
