from __future__ import annotations

from redis.asyncio import Redis

from infrastructure.redis.contracts import TicketStreamConsumer, TicketStreamPublisher
from infrastructure.redis.keys import STREAM_TICKETS_NEW


class RedisTicketStreamPublisher(TicketStreamPublisher):
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def publish_new_ticket(
        self,
        *,
        ticket_id: str,
        client_chat_id: int,
        subject: str,
    ) -> str:
        return await self.redis.xadd(
            STREAM_TICKETS_NEW,
            {
                "ticket_id": ticket_id,
                "client_chat_id": str(client_chat_id),
                "subject": subject,
            },
        )


class RedisTicketStreamConsumer(TicketStreamConsumer):
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def poll_new_tickets(
        self,
        *,
        last_id: str = "0-0",
        count: int = 10,
        block_ms: int | None = None,
    ) -> list[tuple[str, dict[str, str]]]:
        entries = await self.redis.xread(
            {STREAM_TICKETS_NEW: last_id},
            count=count,
            block=block_ms,
        )
        if not entries:
            return []

        _, stream_messages = entries[0]
        # TODO: switch to consumer groups and acknowledgements when background workers are introduced.
        return [(message_id, dict(payload)) for message_id, payload in stream_messages]
