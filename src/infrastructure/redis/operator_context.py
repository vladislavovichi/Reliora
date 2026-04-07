from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from redis.asyncio import Redis

from infrastructure.redis.contracts import OperatorActiveTicketStore, TicketLiveSession, TicketLiveSessionStore
from infrastructure.redis.keys import operator_active_ticket_key, ticket_live_session_key

LIVE_SESSION_TTL_SECONDS = 60 * 60 * 24 * 30

_CLEAR_IF_MATCHES_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
end
return 0
"""


class RedisTicketLiveSessionStore(TicketLiveSessionStore, OperatorActiveTicketStore):
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def get_session(self, *, ticket_public_id: str) -> TicketLiveSession | None:
        data = await self.redis.hgetall(ticket_live_session_key(ticket_public_id))
        if not data:
            return None
        return _parse_ticket_live_session(data)

    async def refresh_session(
        self,
        *,
        ticket_public_id: str,
        client_chat_id: int,
        operator_telegram_user_id: int | None,
    ) -> TicketLiveSession:
        last_activity_at = _utcnow()
        key = ticket_live_session_key(ticket_public_id)
        payload = {
            "ticket_public_id": ticket_public_id,
            "client_chat_id": str(client_chat_id),
            "last_activity_at": last_activity_at.isoformat(),
        }

        async with self.redis.pipeline(transaction=True) as pipeline:
            pipeline.hset(key, mapping=payload)
            if operator_telegram_user_id is None:
                pipeline.hdel(key, "operator_telegram_user_id")
            else:
                pipeline.hset(
                    key,
                    mapping={"operator_telegram_user_id": str(operator_telegram_user_id)},
                )
            pipeline.expire(key, LIVE_SESSION_TTL_SECONDS)
            await pipeline.execute()

        return TicketLiveSession(
            ticket_public_id=ticket_public_id,
            client_chat_id=client_chat_id,
            operator_telegram_user_id=operator_telegram_user_id,
            last_activity_at=last_activity_at,
        )

    async def delete_session(self, *, ticket_public_id: str) -> None:
        await self.redis.delete(ticket_live_session_key(ticket_public_id))

    async def get_active_ticket(self, *, operator_id: int) -> str | None:
        value = await self.redis.get(operator_active_ticket_key(operator_id))
        if value is None:
            return None
        return str(value)

    async def set_active_ticket(self, *, operator_id: int, ticket_public_id: str) -> None:
        await self.redis.set(operator_active_ticket_key(operator_id), ticket_public_id)

        live_session_key = ticket_live_session_key(ticket_public_id)
        if not await self.redis.exists(live_session_key):
            return

        async with self.redis.pipeline(transaction=True) as pipeline:
            pipeline.hset(
                live_session_key,
                mapping={
                    "operator_telegram_user_id": str(operator_id),
                    "last_activity_at": _utcnow().isoformat(),
                },
            )
            pipeline.expire(live_session_key, LIVE_SESSION_TTL_SECONDS)
            await pipeline.execute()

    async def clear(self, *, operator_id: int) -> None:
        await self.redis.delete(operator_active_ticket_key(operator_id))

    async def clear_if_matches(self, *, operator_id: int, ticket_public_id: str) -> None:
        await cast(
            Any,
            self.redis.eval(
                _CLEAR_IF_MATCHES_SCRIPT,
                1,
                operator_active_ticket_key(operator_id),
                ticket_public_id,
            ),
        )


def _parse_ticket_live_session(data: dict[str, Any]) -> TicketLiveSession:
    last_activity_raw = data.get("last_activity_at")
    if isinstance(last_activity_raw, bytes):
        last_activity_raw = last_activity_raw.decode("utf-8")
    if not isinstance(last_activity_raw, str):
        raise RuntimeError("В Redis live session отсутствует last_activity_at.")

    operator_raw = data.get("operator_telegram_user_id")
    if isinstance(operator_raw, bytes):
        operator_raw = operator_raw.decode("utf-8")

    ticket_public_id = data.get("ticket_public_id")
    if isinstance(ticket_public_id, bytes):
        ticket_public_id = ticket_public_id.decode("utf-8")
    if not isinstance(ticket_public_id, str):
        raise RuntimeError("В Redis live session отсутствует ticket_public_id.")

    client_chat_id = data.get("client_chat_id")
    if isinstance(client_chat_id, bytes):
        client_chat_id = client_chat_id.decode("utf-8")
    if not isinstance(client_chat_id, str):
        raise RuntimeError("В Redis live session отсутствует client_chat_id.")

    return TicketLiveSession(
        ticket_public_id=ticket_public_id,
        client_chat_id=int(client_chat_id),
        operator_telegram_user_id=int(operator_raw) if isinstance(operator_raw, str) else None,
        last_activity_at=datetime.fromisoformat(last_activity_raw),
    )


def _utcnow() -> datetime:
    return datetime.now(UTC)
