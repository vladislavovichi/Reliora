from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol
from uuid import UUID

from domain.entities.ticket import Ticket
from domain.enums.tickets import (
    TicketEventType,
    TicketMessageSenderType,
    TicketPriority,
    TicketStatus,
)


class TicketRepository(Protocol):
    async def create(
        self,
        *,
        client_chat_id: int,
        subject: str,
        priority: TicketPriority = TicketPriority.NORMAL,
    ) -> Ticket:
        """Create and return a new ticket."""

    async def get_by_public_id(self, public_id: UUID) -> Ticket | None:
        """Return a ticket by its public identifier."""

    async def get_active_by_client_chat_id(self, client_chat_id: int) -> Ticket | None:
        """Return the most recent open ticket for a client chat, if any."""

    async def enqueue(self, *, ticket_public_id: UUID) -> Ticket | None:
        """Move a ticket into the queue."""

    async def assign_to_operator(
        self, *, ticket_public_id: UUID, operator_id: int
    ) -> Ticket | None:
        """Assign a ticket to an operator and update its status."""

    async def escalate(self, *, ticket_public_id: UUID) -> Ticket | None:
        """Escalate a ticket and persist its new status."""

    async def close(self, *, ticket_public_id: UUID) -> Ticket | None:
        """Close a ticket and persist its closure timestamp."""

    async def count_by_status(self) -> Mapping[TicketStatus, int]:
        """Return ticket counts grouped by status."""


class TicketMessageRepository(Protocol):
    async def add(
        self,
        *,
        ticket_id: int,
        telegram_message_id: int,
        sender_type: TicketMessageSenderType,
        text: str,
        sender_operator_id: int | None = None,
    ) -> None:
        """Persist a ticket message."""


class OperatorRepository(Protocol):
    async def get_or_create(
        self,
        *,
        telegram_user_id: int,
        display_name: str,
        username: str | None = None,
    ) -> int:
        """Return an operator identifier, creating or refreshing the operator record if needed."""


class TagRepository(Protocol):
    async def get_or_create(self, *, name: str) -> int:
        """Return a tag identifier, creating the tag if it does not exist."""


class TicketEventRepository(Protocol):
    async def add(
        self,
        *,
        ticket_id: int,
        event_type: TicketEventType,
        payload_json: Mapping[str, object] | None = None,
    ) -> None:
        """Persist a workflow event for a ticket."""
