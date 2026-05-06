from __future__ import annotations

from redis.asyncio import Redis

from application.contracts.runtime import (
    TicketStreamConsumer,
    TicketStreamMessage,
    TicketStreamPublisher,
)
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
        message_id = await self.redis.xadd(
            STREAM_TICKETS_NEW,
            {
                "ticket_id": ticket_id,
                "client_chat_id": str(client_chat_id),
                "subject": subject,
            },
        )
        return str(message_id)


class RedisTicketStreamConsumer(TicketStreamConsumer):
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def read_new_ticket_messages(
        self,
        *,
        last_id: str = "0-0",
        count: int = 10,
        block_ms: int | None = None,
    ) -> list[TicketStreamMessage]:
        entries = await self.redis.xread(
            {STREAM_TICKETS_NEW: last_id},
            count=count,
            block=block_ms,
        )
        if not entries:
            return []

        _, stream_messages = entries[0]
        return [
            TicketStreamMessage(
                message_id=str(message_id),
                ticket_id=str(payload["ticket_id"]),
                client_chat_id=int(payload["client_chat_id"]),
                subject=str(payload["subject"]),
            )
            for message_id, payload in stream_messages
        ]

    async def poll_new_tickets(
        self,
        *,
        last_id: str = "0-0",
        count: int = 10,
        block_ms: int | None = None,
    ) -> list[tuple[str, dict[str, str]]]:
        messages = await self.read_new_ticket_messages(
            last_id=last_id,
            count=count,
            block_ms=block_ms,
        )
        return [
            (
                message.message_id,
                {
                    "ticket_id": message.ticket_id,
                    "client_chat_id": str(message.client_chat_id),
                    "subject": message.subject,
                },
            )
            for message in messages
        ]
