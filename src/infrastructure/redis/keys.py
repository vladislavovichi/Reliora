from __future__ import annotations

STREAM_TICKETS_NEW = "streams:tickets:new"
GLOBAL_RATE_LIMIT_KEY = "rl:global"
SLA_DEADLINES_KEY = "zset:sla_deadlines"


def ticket_lock_key(ticket_id: str | int) -> str:
    return f"locks:ticket:{ticket_id}"


def chat_rate_limit_key(chat_id: int) -> str:
    return f"rl:chat:{chat_id}"


def operator_presence_key(operator_id: int) -> str:
    return f"presence:operator:{operator_id}"


def operator_active_ticket_key(operator_id: int) -> str:
    return f"operator:{operator_id}:active_ticket"


def ticket_live_session_key(ticket_public_id: str) -> str:
    return f"ticket:{ticket_public_id}:live_session"
