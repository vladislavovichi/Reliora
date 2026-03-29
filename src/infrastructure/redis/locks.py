from __future__ import annotations

from typing import Any, cast
from uuid import uuid4

from redis.asyncio import Redis

from infrastructure.redis.contracts import TicketLock, TicketLockManager
from infrastructure.redis.keys import ticket_lock_key

_RELEASE_LOCK_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
end
return 0
"""


class RedisTicketLock(TicketLock):
    def __init__(self, redis: Redis, *, key: str) -> None:
        self.redis = redis
        self.key = key
        self.token = uuid4().hex
        self._is_acquired = False

    async def acquire(self, *, ttl_seconds: int = 30) -> bool:
        acquired = await self.redis.set(self.key, self.token, ex=ttl_seconds, nx=True)
        self._is_acquired = bool(acquired)
        return self._is_acquired

    async def release(self) -> None:
        if not self._is_acquired:
            return

        await cast(Any, self.redis.eval(_RELEASE_LOCK_SCRIPT, 1, self.key, self.token))
        self._is_acquired = False


class RedisTicketLockManager(TicketLockManager):
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    def for_ticket(self, ticket_id: str | int) -> TicketLock:
        return RedisTicketLock(self.redis, key=ticket_lock_key(ticket_id))
