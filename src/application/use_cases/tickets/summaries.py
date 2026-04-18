from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from application.use_cases.tickets.identifiers import format_public_ticket_number
from application.use_cases.tickets.message_content import build_ticket_mini_title
from domain.contracts.repositories import OperatorRecord
from domain.entities.ticket import (
    Ticket,
    TicketAttachmentDetails,
    TicketHistoryEntry,
    TicketInternalNoteDetails,
    TicketMessageDetails,
)
from domain.entities.ticket import TicketDetails as DomainTicketDetails
from domain.enums.roles import UserRole
from domain.enums.tickets import (
    TicketAttachmentKind,
    TicketEventType,
    TicketMessageSenderType,
    TicketSentiment,
    TicketSignalConfidence,
    TicketStatus,
)


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
class TicketFeedbackSummary:
    public_id: UUID
    public_number: str
    client_chat_id: int
    rating: int
    comment: str | None
    submitted_at: datetime


class TicketFeedbackMutationStatus(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    ALREADY_RECORDED = "already_recorded"
    MISSING = "missing"
    NOT_FOUND = "not_found"
    NOT_CLOSED = "not_closed"
    NOT_ALLOWED = "not_allowed"


@dataclass(slots=True)
class TicketFeedbackMutationResult:
    status: TicketFeedbackMutationStatus
    feedback: TicketFeedbackSummary | None = None


@dataclass(slots=True)
class QueuedTicketSummary:
    public_id: UUID
    public_number: str
    subject: str
    priority: str
    status: TicketStatus
    category_title: str | None = None


def build_queued_ticket_summary(ticket: Ticket) -> QueuedTicketSummary:
    return QueuedTicketSummary(
        public_id=ticket.public_id,
        public_number=format_public_ticket_number(ticket.public_id),
        subject=ticket.subject,
        priority=ticket.priority.value,
        status=ticket.status,
    )


@dataclass(slots=True)
class OperatorTicketSummary:
    public_id: UUID
    public_number: str
    subject: str
    priority: str
    status: TicketStatus
    category_title: str | None = None


def build_operator_ticket_summary(ticket: Ticket) -> OperatorTicketSummary:
    return OperatorTicketSummary(
        public_id=ticket.public_id,
        public_number=format_public_ticket_number(ticket.public_id),
        subject=ticket.subject,
        priority=ticket.priority.value,
        status=ticket.status,
    )


@dataclass(slots=True)
class HistoricalTicketSummary:
    public_id: UUID
    public_number: str
    status: TicketStatus
    created_at: datetime
    closed_at: datetime | None
    mini_title: str
    category_id: int | None = None
    category_code: str | None = None
    category_title: str | None = None


def build_historical_ticket_summary(ticket: TicketHistoryEntry) -> HistoricalTicketSummary:
    return HistoricalTicketSummary(
        public_id=ticket.public_id,
        public_number=format_public_ticket_number(ticket.public_id),
        status=ticket.status,
        created_at=ticket.created_at,
        closed_at=ticket.closed_at,
        mini_title=build_ticket_mini_title(
            text=ticket.first_client_message_text,
            attachment=ticket.first_client_message_attachment,
            fallback=ticket.subject,
        ),
        category_id=ticket.category_id,
        category_code=ticket.category_code,
        category_title=ticket.category_title,
    )


@dataclass(slots=True)
class TicketAttachmentSummary:
    kind: TicketAttachmentKind
    telegram_file_id: str
    telegram_file_unique_id: str | None
    filename: str | None
    mime_type: str | None
    storage_path: str | None = None


def build_ticket_attachment_summary(
    attachment: TicketAttachmentDetails,
) -> TicketAttachmentSummary:
    return TicketAttachmentSummary(
        kind=attachment.kind,
        telegram_file_id=attachment.telegram_file_id,
        telegram_file_unique_id=attachment.telegram_file_unique_id,
        filename=attachment.filename,
        mime_type=attachment.mime_type,
        storage_path=attachment.storage_path,
    )


@dataclass(slots=True)
class TicketMessageSummary:
    sender_type: TicketMessageSenderType
    sender_operator_id: int | None
    sender_operator_name: str | None
    text: str | None
    created_at: datetime
    attachment: TicketAttachmentSummary | None = None
    sentiment: TicketSentiment | None = None
    sentiment_confidence: TicketSignalConfidence | None = None
    sentiment_reason: str | None = None
    duplicate_count: int = 0
    last_duplicate_at: datetime | None = None


def build_ticket_message_summary(message: TicketMessageDetails) -> TicketMessageSummary:
    return TicketMessageSummary(
        sender_type=message.sender_type,
        sender_operator_id=message.sender_operator_id,
        sender_operator_name=message.sender_operator_name,
        text=message.text,
        attachment=(
            build_ticket_attachment_summary(message.attachment)
            if message.attachment is not None
            else None
        ),
        created_at=message.created_at,
        sentiment=message.sentiment,
        sentiment_confidence=message.sentiment_confidence,
        sentiment_reason=message.sentiment_reason,
        duplicate_count=message.duplicate_count,
        last_duplicate_at=message.last_duplicate_at,
    )


@dataclass(slots=True)
class TicketInternalNoteSummary:
    id: int
    author_operator_id: int
    author_operator_name: str | None
    text: str
    created_at: datetime


def build_ticket_internal_note_summary(
    note: TicketInternalNoteDetails,
) -> TicketInternalNoteSummary:
    return TicketInternalNoteSummary(
        id=note.id,
        author_operator_id=note.author_operator_id,
        author_operator_name=note.author_operator_name,
        text=note.text,
        created_at=note.created_at,
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
    closed_at: datetime | None = None
    assigned_operator_username: str | None = None
    category_id: int | None = None
    category_code: str | None = None
    category_title: str | None = None
    sentiment: TicketSentiment | None = None
    sentiment_confidence: TicketSignalConfidence | None = None
    sentiment_reason: str | None = None
    sentiment_detected_at: datetime | None = None
    tags: tuple[str, ...] = ()
    last_message_text: str | None = None
    last_message_sender_type: TicketMessageSenderType | None = None
    last_message_attachment: TicketAttachmentSummary | None = None
    message_history: tuple[TicketMessageSummary, ...] = ()
    internal_notes: tuple[TicketInternalNoteSummary, ...] = ()


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
        assigned_operator_username=ticket.assigned_operator_username,
        created_at=ticket.created_at,
        closed_at=ticket.closed_at,
        category_id=ticket.category_id,
        category_code=ticket.category_code,
        category_title=ticket.category_title,
        sentiment=ticket.sentiment,
        sentiment_confidence=ticket.sentiment_confidence,
        sentiment_reason=ticket.sentiment_reason,
        sentiment_detected_at=ticket.sentiment_detected_at,
        tags=ticket.tags,
        last_message_text=ticket.last_message_text,
        last_message_sender_type=ticket.last_message_sender_type,
        last_message_attachment=(
            build_ticket_attachment_summary(ticket.last_message_attachment)
            if ticket.last_message_attachment is not None
            else None
        ),
        message_history=tuple(
            build_ticket_message_summary(message) for message in ticket.message_history
        ),
        internal_notes=tuple(
            build_ticket_internal_note_summary(note) for note in ticket.internal_notes
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
class AccessContextSummary:
    telegram_user_id: int
    role: UserRole


@dataclass(slots=True)
class MacroSummary:
    id: int
    title: str
    body: str


@dataclass(slots=True)
class TagSummary:
    id: int
    name: str


@dataclass(slots=True)
class TicketCategorySummary:
    id: int
    code: str
    title: str
    is_active: bool
    sort_order: int


@dataclass(slots=True)
class MacroApplicationResult:
    ticket: TicketSummary
    client_chat_id: int
    macro: MacroSummary


class MacroManagementError(Exception):
    """Raised when a macro management action cannot be completed."""


class CategoryManagementError(Exception):
    """Raised when a category management action cannot be completed."""


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
