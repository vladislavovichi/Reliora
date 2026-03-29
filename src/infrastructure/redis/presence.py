from __future__ import annotations

from redis.asyncio import Redis

from infrastructure.redis.contracts import OperatorPresenceHelper
from infrastructure.redis.keys import operator_presence_key


class RedisOperatorPresenceHelper(OperatorPresenceHelper):
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def touch(self, *, operator_id: int, ttl_seconds: int = 120) -> None:
        await self.redis.set(operator_presence_key(operator_id), "online", ex=ttl_seconds)

    async def is_online(self, *, operator_id: int) -> bool:
        return bool(await self.redis.exists(operator_presence_key(operator_id)))

    async def clear(self, *, operator_id: int) -> None:
        await self.redis.delete(operator_presence_key(operator_id))
