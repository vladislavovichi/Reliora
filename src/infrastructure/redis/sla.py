from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from redis.asyncio import Redis

from application.contracts.runtime import SLADeadlineScheduler, SLATimeoutProcessor
from infrastructure.redis.keys import SLA_DEADLINES_KEY

_CLAIM_DUE_SCRIPT = """
local items = redis.call('ZRANGEBYSCORE', KEYS[1], '-inf', ARGV[1], 'LIMIT', 0, tonumber(ARGV[2]))
if #items > 0 then
    redis.call('ZREM', KEYS[1], unpack(items))
end
return items
"""


class RedisSLADeadlineScheduler(SLADeadlineScheduler):
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def schedule(self, *, ticket_id: str, deadline_at: datetime) -> None:
        await self.redis.zadd(SLA_DEADLINES_KEY, {ticket_id: deadline_at.timestamp()})

    async def cancel(self, *, ticket_id: str) -> None:
        await self.redis.zrem(SLA_DEADLINES_KEY, ticket_id)

    async def get_due(self, *, until: datetime, limit: int = 100) -> Sequence[str]:
        items = await self.redis.zrangebyscore(
            SLA_DEADLINES_KEY,
            min="-inf",
            max=until.timestamp(),
            start=0,
            num=limit,
        )
        return list(items)

    async def claim_due(self, *, until: datetime, limit: int = 100) -> Sequence[str]:
        result = await self.redis.eval(
            _CLAIM_DUE_SCRIPT,
            1,
            SLA_DEADLINES_KEY,
            until.timestamp(),
            limit,
        )
        return [r.decode() if isinstance(r, bytes) else r for r in result]


class RedisSLATimeoutProcessor(SLATimeoutProcessor):
    def __init__(self, scheduler: SLADeadlineScheduler) -> None:
        self.scheduler = scheduler

    async def claim_due_ticket_ids(self, *, limit: int = 100) -> Sequence[str]:
        return list(
            await self.scheduler.claim_due(
                until=datetime.now(UTC),
                limit=limit,
            )
        )

    async def run_once(self, *, limit: int = 100) -> int:
        due_ticket_ids = await self.claim_due_ticket_ids(
            limit=limit,
        )
        return len(due_ticket_ids)
