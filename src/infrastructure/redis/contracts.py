from __future__ import annotations

from collections.abc import Sequence
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
