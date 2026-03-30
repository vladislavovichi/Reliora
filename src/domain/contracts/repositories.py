from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol
from uuid import UUID

from domain.entities.ticket import Ticket, TicketDetails
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

    async def get_details_by_public_id(self, public_id: UUID) -> TicketDetails | None:
        """Return ticket details enriched for operator-facing workflows."""

    async def get_active_by_client_chat_id(self, client_chat_id: int) -> Ticket | None:
        """Return the most recent open ticket for a client chat, if any."""

    async def get_next_queued_ticket(
        self, *, prioritize_priority: bool = False
    ) -> Ticket | None:
        """Return the next queued ticket according to the queue ordering."""

    async def list_queued_tickets(
        self,
        *,
        limit: int | None = None,
        prioritize_priority: bool = False,
    ) -> Sequence[Ticket]:
        """Return queued tickets in queue order."""

    async def enqueue(self, *, ticket_public_id: UUID) -> Ticket | None:
        """Move a ticket into the queue."""

    async def assign_queued_to_operator(
        self, *, ticket_public_id: UUID, operator_id: int
    ) -> Ticket | None:
        """Assign a queued ticket to an operator only if it is still queued."""

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

    async def allocate_internal_telegram_message_id(
        self,
        *,
        ticket_id: int,
        sender_type: TicketMessageSenderType,
    ) -> int:
        """Return a negative internal message id suitable for synthetic ticket messages."""


class OperatorRepository(Protocol):
    async def get_or_create(
        self,
        *,
        telegram_user_id: int,
        display_name: str,
        username: str | None = None,
    ) -> int:
        """Return an operator identifier, creating or refreshing the operator record if needed."""


class MacroRecord(Protocol):
    id: int
    title: str
    body: str


class MacroRepository(Protocol):
    async def list_all(self) -> Sequence[MacroRecord]:
        """Return configured operator macros."""

    async def get_by_id(self, *, macro_id: int) -> MacroRecord | None:
        """Return a macro by identifier."""


class TagRecord(Protocol):
    id: int
    name: str


class TagRepository(Protocol):
    async def get_or_create(self, *, name: str) -> int:
        """Return a tag identifier, creating the tag if it does not exist."""

    async def get_by_name(self, *, name: str) -> TagRecord | None:
        """Return a tag by name."""

    async def list_all(self) -> Sequence[TagRecord]:
        """Return configured tags."""


class TicketTagRepository(Protocol):
    async def list_for_ticket(self, *, ticket_id: int) -> Sequence[TagRecord]:
        """Return tags attached to a ticket."""

    async def add(self, *, ticket_id: int, tag_id: int) -> bool:
        """Attach a tag to a ticket and report whether a new link was created."""

    async def remove(self, *, ticket_id: int, tag_id: int) -> bool:
        """Detach a tag from a ticket and report whether a link was removed."""


class TicketEventRepository(Protocol):
    async def add(
        self,
        *,
        ticket_id: int,
        event_type: TicketEventType,
        payload_json: Mapping[str, object] | None = None,
    ) -> None:
        """Persist a workflow event for a ticket."""
