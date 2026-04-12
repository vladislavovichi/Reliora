from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from domain.entities.ai import TicketAISummaryDetails
from domain.entities.feedback import TicketFeedback
from domain.entities.ticket import (
    Ticket,
    TicketAttachmentDetails,
    TicketDetails,
    TicketEventDetails,
    TicketHistoryEntry,
    TicketInternalNoteDetails,
)
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

    async def list_closed_tickets(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> Sequence[TicketHistoryEntry]:
        """Return archived tickets ordered for historical browsing."""

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


class TicketAnalyticsRepository(Protocol):
    async def count_by_status(self) -> Mapping[TicketStatus, int]:
        """Return current ticket counts grouped by status."""

    async def count_active_tickets_per_operator(self) -> Sequence[OperatorTicketLoadRecord]:
        """Return current non-closed ticket counts grouped by assigned operator."""

    async def count_created_tickets(self, *, since: datetime | None = None) -> int:
        """Return how many tickets were created in the period."""

    async def count_closed_tickets(self, *, since: datetime | None = None) -> int:
        """Return how many tickets were closed in the period."""

    async def get_average_first_response_time_seconds(
        self,
        *,
        since: datetime | None = None,
    ) -> float | None:
        """Return the average first response time in seconds for the period."""

    async def get_average_resolution_time_seconds(
        self,
        *,
        since: datetime | None = None,
    ) -> float | None:
        """Return the average resolution time in seconds for the period."""

    async def count_feedback_submissions(self, *, since: datetime | None = None) -> int:
        """Return how many feedback ratings were submitted in the period."""

    async def get_average_feedback_rating(self, *, since: datetime | None = None) -> float | None:
        """Return the average feedback score in the period."""

    async def get_feedback_rating_distribution(
        self,
        *,
        since: datetime | None = None,
    ) -> Sequence[RatingDistributionRecord]:
        """Return the feedback distribution in the period."""

    async def list_closed_ticket_stats_by_operator(
        self,
        *,
        since: datetime | None = None,
    ) -> Sequence[OperatorClosureStatsRecord]:
        """Return operator performance metrics for tickets closed in the period."""

    async def list_created_ticket_counts_by_category(
        self,
        *,
        since: datetime | None = None,
    ) -> Sequence[CategoryTicketCountRecord]:
        """Return ticket creation counts grouped by category for the period."""

    async def list_open_ticket_counts_by_category(self) -> Sequence[CategoryTicketCountRecord]:
        """Return current open ticket counts grouped by category."""

    async def list_closed_ticket_counts_by_category(
        self,
        *,
        since: datetime | None = None,
    ) -> Sequence[CategoryTicketCountRecord]:
        """Return ticket closure counts grouped by category for the period."""

    async def list_feedback_stats_by_category(
        self,
        *,
        since: datetime | None = None,
    ) -> Sequence[CategoryFeedbackStatsRecord]:
        """Return category feedback aggregates for the period."""

    async def count_sla_breaches(self, *, since: datetime | None = None) -> Mapping[str, int]:
        """Return SLA breach counts grouped by breach type for the period."""

    async def list_sla_breach_counts_by_category(
        self,
        *,
        since: datetime | None = None,
    ) -> Sequence[SLABreachCountRecord]:
        """Return SLA breach counts grouped by category for the period."""


class TicketMessageRepository(Protocol):
    async def add(
        self,
        *,
        ticket_id: int,
        telegram_message_id: int,
        sender_type: TicketMessageSenderType,
        text: str | None,
        attachment: TicketAttachmentDetails | None = None,
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


class TicketInternalNoteRepository(Protocol):
    async def add(
        self,
        *,
        ticket_id: int,
        author_operator_id: int,
        text: str,
    ) -> TicketInternalNoteDetails:
        """Persist an internal note attached to the ticket."""


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


class TicketAISummaryRepository(Protocol):
    async def get_by_ticket_id(self, *, ticket_id: int) -> TicketAISummaryDetails | None:
        """Return the latest stored AI summary for the ticket when it exists."""

    async def upsert(
        self,
        *,
        ticket_id: int,
        short_summary: str,
        user_goal: str,
        actions_taken: str,
        current_status: str,
        generated_at: datetime,
        source_ticket_updated_at: datetime,
        source_message_count: int,
        source_internal_note_count: int,
        model_id: str | None,
    ) -> TicketAISummaryDetails:
        """Create or update the stored AI summary for the ticket."""


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


class OperatorInviteCodeRepository(Protocol):
    async def create(
        self,
        *,
        code_hash: str,
        created_by_telegram_user_id: int,
        expires_at: datetime,
        max_uses: int = 1,
    ) -> OperatorInviteCodeRecord:
        """Persist and return a new operator invite code."""

    async def get_by_code_hash(self, *, code_hash: str) -> OperatorInviteCodeRecord | None:
        """Return an invite code record by its stored hash."""

    async def mark_used(
        self,
        *,
        invite_id: int,
        telegram_user_id: int,
        used_at: datetime,
    ) -> OperatorInviteCodeRecord | None:
        """Increase usage counters and deactivate the invite when the limit is reached."""


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


class OperatorClosureStatsRecord(Protocol):
    @property
    def operator_id(self) -> int:
        """Operator identifier."""

    @property
    def display_name(self) -> str:
        """Operator display name."""

    @property
    def closed_ticket_count(self) -> int:
        """Closed tickets count for the period."""

    @property
    def average_first_response_time_seconds(self) -> float | None:
        """Average first response time in seconds for the period."""

    @property
    def average_resolution_time_seconds(self) -> float | None:
        """Average resolution time in seconds for the period."""

    @property
    def average_satisfaction(self) -> float | None:
        """Average satisfaction score for the period."""

    @property
    def feedback_count(self) -> int:
        """Feedback records count for the period."""


class CategoryTicketCountRecord(Protocol):
    @property
    def category_id(self) -> int | None:
        """Category identifier when present."""

    @property
    def category_title(self) -> str | None:
        """Category title when present."""

    @property
    def ticket_count(self) -> int:
        """Ticket count for the selection."""


class CategoryFeedbackStatsRecord(Protocol):
    @property
    def category_id(self) -> int | None:
        """Category identifier when present."""

    @property
    def category_title(self) -> str | None:
        """Category title when present."""

    @property
    def average_satisfaction(self) -> float | None:
        """Average feedback score for the category."""

    @property
    def feedback_count(self) -> int:
        """Feedback count for the category."""


class RatingDistributionRecord(Protocol):
    @property
    def rating(self) -> int:
        """Feedback rating value."""

    @property
    def count(self) -> int:
        """How many times the rating appears."""


class SLABreachCountRecord(Protocol):
    @property
    def category_id(self) -> int | None:
        """Category identifier when present."""

    @property
    def category_title(self) -> str | None:
        """Category title when present."""

    @property
    def breach_count(self) -> int:
        """Number of SLA breaches for the category."""


class OperatorRecord(Protocol):
    id: int
    telegram_user_id: int
    username: str | None
    display_name: str
    is_active: bool


class OperatorInviteCodeRecord(Protocol):
    id: int
    code_hash: str
    created_by_telegram_user_id: int
    expires_at: datetime
    max_uses: int
    used_count: int
    is_active: bool
    last_used_at: datetime | None
    last_used_telegram_user_id: int | None
    deactivated_at: datetime | None


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

    async def list_for_ticket(self, *, ticket_id: int) -> Sequence[TicketEventDetails]:
        """Return workflow events for the ticket ordered by creation time."""


class AuditLogRepository(Protocol):
    async def add(
        self,
        *,
        action: str,
        entity_type: str,
        outcome: str,
        actor_telegram_user_id: int | None = None,
        entity_id: int | None = None,
        entity_public_id: UUID | None = None,
        correlation_id: str | None = None,
        metadata_json: Mapping[str, object] | None = None,
    ) -> None:
        """Persist a structured audit event."""


class SLAPolicyRecord(Protocol):
    id: int
    name: str
    first_response_minutes: int
    resolution_minutes: int
    priority: TicketPriority | None


class SLAPolicyRepository(Protocol):
    async def get_for_priority(self, *, priority: TicketPriority) -> SLAPolicyRecord | None:
        """Return the best matching SLA policy for a ticket priority."""
