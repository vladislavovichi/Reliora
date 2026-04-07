from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from application.use_cases.tickets.identifiers import format_public_ticket_number
from domain.contracts.repositories import OperatorRecord
from domain.entities.ticket import Ticket, TicketMessageDetails
from domain.entities.ticket import TicketDetails as DomainTicketDetails
from domain.enums.tickets import TicketEventType, TicketMessageSenderType, TicketStatus


@dataclass(slots=True)
class TicketSummary:
    public_id: UUID
    public_number: str
    status: TicketStatus
    created: bool = False
    event_type: TicketEventType | None = None


@dataclass(slots=True)
class TicketStats:
    total: int
    open_total: int
    by_status: dict[TicketStatus, int]


@dataclass(slots=True)
class QueuedTicketSummary:
    public_id: UUID
    public_number: str
    subject: str
    priority: str
    status: TicketStatus


def build_queued_ticket_summary(ticket: Ticket) -> QueuedTicketSummary:
    return QueuedTicketSummary(
        public_id=ticket.public_id,
        public_number=format_public_ticket_number(ticket.public_id),
        subject=ticket.subject,
        priority=ticket.priority.value,
        status=ticket.status,
    )


@dataclass(slots=True)
class TicketMessageSummary:
    sender_type: TicketMessageSenderType
    sender_operator_id: int | None
    sender_operator_name: str | None
    text: str
    created_at: datetime


def build_ticket_message_summary(message: TicketMessageDetails) -> TicketMessageSummary:
    return TicketMessageSummary(
        sender_type=message.sender_type,
        sender_operator_id=message.sender_operator_id,
        sender_operator_name=message.sender_operator_name,
        text=message.text,
        created_at=message.created_at,
    )


@dataclass(slots=True)
class TicketDetailsSummary:
    public_id: UUID
    public_number: str
    client_chat_id: int
    status: TicketStatus
    priority: str
    subject: str
    assigned_operator_id: int | None
    assigned_operator_name: str | None
    assigned_operator_telegram_user_id: int | None
    created_at: datetime
    tags: tuple[str, ...]
    last_message_text: str | None
    last_message_sender_type: TicketMessageSenderType | None
    message_history: tuple[TicketMessageSummary, ...]


def build_ticket_details_summary(ticket: DomainTicketDetails) -> TicketDetailsSummary:
    return TicketDetailsSummary(
        public_id=ticket.public_id,
        public_number=format_public_ticket_number(ticket.public_id),
        client_chat_id=ticket.client_chat_id,
        status=ticket.status,
        priority=ticket.priority.value,
        subject=ticket.subject,
        assigned_operator_id=ticket.assigned_operator_id,
        assigned_operator_name=ticket.assigned_operator_name,
        assigned_operator_telegram_user_id=ticket.assigned_operator_telegram_user_id,
        created_at=ticket.created_at,
        tags=ticket.tags,
        last_message_text=ticket.last_message_text,
        last_message_sender_type=ticket.last_message_sender_type,
        message_history=tuple(
            build_ticket_message_summary(message) for message in ticket.message_history
        ),
    )


@dataclass(slots=True)
class OperatorReplyResult:
    ticket: TicketSummary
    client_chat_id: int


@dataclass(slots=True)
class OperatorSummary:
    telegram_user_id: int
    display_name: str
    username: str | None
    is_active: bool


def build_operator_summary(operator: OperatorRecord) -> OperatorSummary:
    return OperatorSummary(
        telegram_user_id=operator.telegram_user_id,
        display_name=operator.display_name,
        username=operator.username,
        is_active=operator.is_active,
    )


@dataclass(slots=True)
class OperatorRoleMutationResult:
    operator: OperatorSummary
    changed: bool


@dataclass(slots=True)
class MacroSummary:
    id: int
    title: str
    body: str


@dataclass(slots=True)
class MacroApplicationResult:
    ticket: TicketSummary
    client_chat_id: int
    macro: MacroSummary


@dataclass(slots=True)
class TicketTagsSummary:
    public_id: UUID
    public_number: str
    tags: tuple[str, ...]


@dataclass(slots=True)
class TicketTagMutationResult:
    ticket: TicketSummary
    tag: str
    changed: bool
    tags: tuple[str, ...]


class SLADeadlineStatus(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    OK = "ok"
    APPROACHING = "approaching"
    BREACHED = "breached"


@dataclass(slots=True)
class SLADeadlineSummary:
    deadline_at: datetime | None
    status: SLADeadlineStatus
    remaining_seconds: int | None


@dataclass(slots=True)
class TicketSLAEvaluationSummary:
    public_id: UUID
    public_number: str
    status: TicketStatus
    assigned_operator_id: int | None
    policy_name: str | None
    first_response: SLADeadlineSummary
    resolution: SLADeadlineSummary
    stale_assignment: SLADeadlineSummary
    should_auto_escalate: bool
    should_auto_reassign: bool


@dataclass(slots=True, frozen=True)
class SLAAutoReassignmentTarget:
    ticket_public_id: UUID
    telegram_user_id: int
    display_name: str
    username: str | None = None


@dataclass(slots=True)
class TicketSLAProcessingSummary:
    evaluation: TicketSLAEvaluationSummary
    persisted_event_types: tuple[TicketEventType, ...]


@dataclass(slots=True)
class SLABatchProcessingResult:
    processed_tickets: tuple[TicketSLAProcessingSummary, ...]
    evaluated_count: int
    auto_escalated_count: int
    auto_reassigned_count: int


class OperatorManagementError(Exception):
    """Raised when an operator management action is not allowed."""
