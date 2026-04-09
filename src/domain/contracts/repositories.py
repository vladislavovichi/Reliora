from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol
from uuid import UUID

from domain.entities.feedback import TicketFeedback
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
        category_id: int | None = None,
        priority: TicketPriority = TicketPriority.NORMAL,
    ) -> Ticket:
        """Create and return a new ticket."""

    async def get_by_public_id(self, public_id: UUID) -> Ticket | None:
        """Return a ticket by its public identifier."""

    async def get_details_by_public_id(self, public_id: UUID) -> TicketDetails | None:
        """Return ticket details enriched for operator-facing workflows."""

    async def get_active_by_client_chat_id(self, client_chat_id: int) -> Ticket | None:
        """Return the most recent open ticket for a client chat, if any."""

    async def get_next_queued_ticket(self, *, prioritize_priority: bool = False) -> Ticket | None:
        """Return the next queued ticket according to the queue ordering."""

    async def list_queued_tickets(
        self,
        *,
        limit: int | None = None,
        prioritize_priority: bool = False,
    ) -> Sequence[Ticket]:
        """Return queued tickets in queue order."""

    async def list_open_tickets(self, *, limit: int | None = None) -> Sequence[Ticket]:
        """Return open tickets that are eligible for workflow evaluation."""

    async def list_open_tickets_for_operator(
        self,
        *,
        operator_telegram_user_id: int,
        limit: int | None = None,
    ) -> Sequence[Ticket]:
        """Return open tickets currently assigned to the operator."""

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

    async def count_active_tickets_per_operator(self) -> Sequence[OperatorTicketLoadRecord]:
        """Return current non-closed ticket counts grouped by assigned operator."""

    async def get_average_first_response_time_seconds(self) -> float | None:
        """Return the average first response time in seconds using ticket timestamps."""

    async def get_average_resolution_time_seconds(self) -> float | None:
        """Return the average resolution time in seconds using ticket timestamps."""


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


class TicketFeedbackRepository(Protocol):
    async def get_by_ticket_id(self, *, ticket_id: int) -> TicketFeedback | None:
        """Return feedback for the ticket when it exists."""

    async def create(
        self,
        *,
        ticket_id: int,
        client_chat_id: int,
        rating: int,
    ) -> TicketFeedback:
        """Persist the first feedback rating for a ticket."""

    async def update_comment(
        self,
        *,
        ticket_id: int,
        comment: str,
    ) -> TicketFeedback | None:
        """Persist a feedback comment for the ticket."""


class OperatorRepository(Protocol):
    async def exists_active_by_telegram_user_id(self, *, telegram_user_id: int) -> bool:
        """Return whether the Telegram user is an active operator."""

    async def list_active(self) -> Sequence[OperatorRecord]:
        """Return active operators ordered for admin-facing views."""

    async def promote(
        self,
        *,
        telegram_user_id: int,
        display_name: str,
        username: str | None = None,
    ) -> OperatorRecord:
        """Grant operator rights to a Telegram user, creating or reactivating the record."""

    async def revoke(self, *, telegram_user_id: int) -> OperatorRecord | None:
        """Revoke operator rights from an active operator."""

    async def get_or_create(
        self,
        *,
        telegram_user_id: int,
        display_name: str,
        username: str | None = None,
    ) -> int:
        """Return an operator identifier, creating or refreshing the operator record if needed."""


class OperatorTicketLoadRecord(Protocol):
    @property
    def operator_id(self) -> int:
        """Operator identifier."""

    @property
    def display_name(self) -> str:
        """Operator display name."""

    @property
    def ticket_count(self) -> int:
        """Current active ticket count."""


class OperatorRecord(Protocol):
    id: int
    telegram_user_id: int
    username: str | None
    display_name: str
    is_active: bool


class MacroRecord(Protocol):
    id: int
    title: str
    body: str


class TicketCategoryRecord(Protocol):
    id: int
    code: str
    title: str
    is_active: bool
    sort_order: int


class TicketCategoryRepository(Protocol):
    async def list_all(self, *, include_inactive: bool = True) -> Sequence[TicketCategoryRecord]:
        """Return configured ticket categories ordered for navigation and analytics."""

    async def get_by_id(self, *, category_id: int) -> TicketCategoryRecord | None:
        """Return a category by identifier."""

    async def get_by_code(self, *, code: str) -> TicketCategoryRecord | None:
        """Return a category by code."""

    async def create(
        self,
        *,
        code: str,
        title: str,
        sort_order: int,
        is_active: bool = True,
    ) -> TicketCategoryRecord:
        """Create and return a category."""

    async def update_title(
        self,
        *,
        category_id: int,
        title: str,
    ) -> TicketCategoryRecord | None:
        """Update a category title and return the stored record."""

    async def set_active(
        self,
        *,
        category_id: int,
        is_active: bool,
    ) -> TicketCategoryRecord | None:
        """Toggle a category availability flag and return the stored record."""

    async def get_next_sort_order(self) -> int:
        """Return the next available sort order for a new category."""


class MacroRepository(Protocol):
    async def list_all(self) -> Sequence[MacroRecord]:
        """Return configured operator macros."""

    async def get_by_id(self, *, macro_id: int) -> MacroRecord | None:
        """Return a macro by identifier."""

    async def get_by_title(self, *, title: str) -> MacroRecord | None:
        """Return a macro by title."""

    async def create(self, *, title: str, body: str) -> MacroRecord:
        """Create and return a macro."""

    async def update_title(self, *, macro_id: int, title: str) -> MacroRecord | None:
        """Update a macro title and return the stored record."""

    async def update_body(self, *, macro_id: int, body: str) -> MacroRecord | None:
        """Update a macro body and return the stored record."""

    async def delete(self, *, macro_id: int) -> MacroRecord | None:
        """Delete a macro and return the removed record."""


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

    async def exists(self, *, ticket_id: int, event_type: TicketEventType) -> bool:
        """Return whether the ticket already has an event of the given type."""


class SLAPolicyRecord(Protocol):
    id: int
    name: str
    first_response_minutes: int
    resolution_minutes: int
    priority: TicketPriority | None


class SLAPolicyRepository(Protocol):
    async def get_for_priority(self, *, priority: TicketPriority) -> SLAPolicyRecord | None:
        """Return the best matching SLA policy for a ticket priority."""
