from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


class TicketLock(Protocol):
    async def acquire(self, *, ttl_seconds: int = 30) -> bool:
        """Try to acquire a ticket lock."""

    async def release(self) -> None:
        """Release a ticket lock if it is owned by this instance."""


class TicketLockManager(Protocol):
    def for_ticket(self, ticket_id: str | int) -> TicketLock:
        """Return a lock helper bound to a specific ticket."""


class GlobalRateLimiter(Protocol):
    async def allow(self) -> bool:
        """Return whether a global operation is allowed."""


class ChatRateLimiter(Protocol):
    async def allow(self, *, chat_id: int) -> bool:
        """Return whether a chat-scoped operation is allowed."""


class OperatorPresenceHelper(Protocol):
    async def touch(self, *, operator_id: int, ttl_seconds: int = 120) -> None:
        """Mark an operator as online for a short TTL window."""

    async def is_online(self, *, operator_id: int) -> bool:
        """Return whether an operator is currently considered online."""

    async def clear(self, *, operator_id: int) -> None:
        """Clear operator presence information."""


class OperatorActiveTicketStore(Protocol):
    async def get_active_ticket(self, *, operator_id: int) -> str | None:
        """Return the public ticket id currently active for the operator."""

    async def set_active_ticket(self, *, operator_id: int, ticket_public_id: str) -> None:
        """Persist the active public ticket id for the operator."""

    async def clear(self, *, operator_id: int) -> None:
        """Clear the active ticket context for the operator."""

    async def clear_if_matches(self, *, operator_id: int, ticket_public_id: str) -> None:
        """Clear the active context if it still points to the provided ticket id."""


@dataclass(slots=True, frozen=True)
class TicketLiveSession:
    ticket_public_id: str
    client_chat_id: int
    operator_telegram_user_id: int | None
    last_activity_at: datetime


class TicketLiveSessionStore(Protocol):
    async def get_session(self, *, ticket_public_id: str) -> TicketLiveSession | None:
        """Return the current live session metadata for the ticket."""

    async def refresh_session(
        self,
        *,
        ticket_public_id: str,
        client_chat_id: int,
        operator_telegram_user_id: int | None,
    ) -> TicketLiveSession:
        """Create or refresh the ticket-scoped live session."""

    async def delete_session(self, *, ticket_public_id: str) -> None:
        """Remove the live session for the ticket."""


class SLADeadlineScheduler(Protocol):
    async def schedule(self, *, ticket_id: str, deadline_at: datetime) -> None:
        """Schedule an SLA deadline."""

    async def cancel(self, *, ticket_id: str) -> None:
        """Cancel an SLA deadline."""

    async def get_due(self, *, until: datetime, limit: int = 100) -> Sequence[str]:
        """Return due ticket identifiers."""


class TicketStreamPublisher(Protocol):
    async def publish_new_ticket(
        self,
        *,
        ticket_id: str,
        client_chat_id: int,
        subject: str,
    ) -> str:
        """Publish a new-ticket event to Redis streams."""


class TicketStreamConsumer(Protocol):
    async def poll_new_tickets(
        self,
        *,
        last_id: str = "0-0",
        count: int = 10,
        block_ms: int | None = None,
    ) -> list[tuple[str, dict[str, str]]]:
        """Read new-ticket events from the Redis stream."""


class SLATimeoutProcessor(Protocol):
    async def run_once(self, *, limit: int = 100) -> int:
        """Run a single SLA timeout processing iteration."""
