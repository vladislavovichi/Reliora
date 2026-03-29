from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from redis.asyncio import Redis

from infrastructure.redis.contracts import SLADeadlineScheduler, SLATimeoutProcessor
from infrastructure.redis.keys import SLA_DEADLINES_KEY


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


class RedisSLATimeoutProcessor(SLATimeoutProcessor):
    def __init__(self, scheduler: SLADeadlineScheduler) -> None:
        self.scheduler = scheduler

    async def run_once(self, *, limit: int = 100) -> int:
        due_ticket_ids = await self.scheduler.get_due(
            until=datetime.now(UTC),
            limit=limit,
        )
        # TODO: fan out SLA timeout events into queue/stream processing when workflow workers exist.
        return len(due_ticket_ids)
