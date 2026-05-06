from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from redis.asyncio import Redis

from application.contracts.runtime import SLADeadlineScheduler, SLATimeoutProcessor
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

    async def claim_due(self, *, until: datetime, limit: int = 100) -> Sequence[str]:
        due_ticket_ids = list(await self.get_due(until=until, limit=limit))
        if not due_ticket_ids:
            return []
        await self.redis.zrem(SLA_DEADLINES_KEY, *due_ticket_ids)
        return due_ticket_ids


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
