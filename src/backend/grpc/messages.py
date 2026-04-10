from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True, frozen=True)
class RequestActorMessage:
    telegram_user_id: int


@dataclass(slots=True, frozen=True)
class OperatorIdentityMessage:
    telegram_user_id: int
    display_name: str
    username: str | None


@dataclass(slots=True, frozen=True)
class TicketAttachmentMessage:
    kind: str
    telegram_file_id: str
    telegram_file_unique_id: str | None
    filename: str | None
    mime_type: str | None
    storage_path: str | None


@dataclass(slots=True, frozen=True)
class ClientTicketMessageCommandMessage:
    client_chat_id: int
    telegram_message_id: int
    text: str | None
    attachment: TicketAttachmentMessage | None
    category_id: int | None


@dataclass(slots=True, frozen=True)
class OperatorTicketReplyCommandMessage:
    ticket_public_id: str
    operator: OperatorIdentityMessage
    telegram_message_id: int
    text: str | None
    attachment: TicketAttachmentMessage | None


@dataclass(slots=True, frozen=True)
class TicketAssignmentCommandMessage:
    ticket_public_id: str
    operator: OperatorIdentityMessage


@dataclass(slots=True, frozen=True)
class AssignNextQueuedTicketCommandMessage:
    operator: OperatorIdentityMessage
    prioritize_priority: bool


@dataclass(slots=True, frozen=True)
class ApplyMacroToTicketCommandMessage:
    ticket_public_id: str
    macro_id: int
    operator: OperatorIdentityMessage


@dataclass(slots=True, frozen=True)
class TicketSummaryMessage:
    public_id: str
    public_number: str
    status: str
    created: bool
    event_type: str | None


@dataclass(slots=True, frozen=True)
class QueuedTicketSummaryMessage:
    public_id: str
    public_number: str
    subject: str
    priority: str
    status: str
    category_title: str | None


@dataclass(slots=True, frozen=True)
class OperatorTicketSummaryMessage:
    public_id: str
    public_number: str
    subject: str
    priority: str
    status: str
    category_title: str | None


@dataclass(slots=True, frozen=True)
class TicketCategorySummaryMessage:
    id: int
    code: str
    title: str
    is_active: bool
    sort_order: int


@dataclass(slots=True, frozen=True)
class TicketMessageSummaryMessage:
    sender_type: str
    sender_operator_id: int | None
    sender_operator_name: str | None
    text: str | None
    created_at: datetime
    attachment: TicketAttachmentMessage | None


@dataclass(slots=True, frozen=True)
class TicketInternalNoteSummaryMessage:
    id: int
    author_operator_id: int
    author_operator_name: str | None
    text: str
    created_at: datetime


@dataclass(slots=True, frozen=True)
class TicketDetailsSummaryMessage:
    public_id: str
    public_number: str
    client_chat_id: int
    status: str
    priority: str
    subject: str
    assigned_operator_id: int | None
    assigned_operator_name: str | None
    assigned_operator_telegram_user_id: int | None
    created_at: datetime
    category_id: int | None
    category_code: str | None
    category_title: str | None
    tags: tuple[str, ...]
    last_message_text: str | None
    last_message_sender_type: str | None
    last_message_attachment: TicketAttachmentMessage | None
    message_history: tuple[TicketMessageSummaryMessage, ...]
    internal_notes: tuple[TicketInternalNoteSummaryMessage, ...]


@dataclass(slots=True, frozen=True)
class OperatorReplyResultMessage:
    ticket: TicketSummaryMessage
    client_chat_id: int


@dataclass(slots=True, frozen=True)
class MacroSummaryMessage:
    id: int
    title: str
    body: str


@dataclass(slots=True, frozen=True)
class MacroApplicationResultMessage:
    ticket: TicketSummaryMessage
    client_chat_id: int
    macro: MacroSummaryMessage


@dataclass(slots=True, frozen=True)
class TicketReportExportMessage:
    format: str
    filename: str
    content_type: str
    content: bytes
    report_public_number: str


@dataclass(slots=True, frozen=True)
class OperatorTicketLoadMessage:
    operator_id: int
    display_name: str
    ticket_count: int


@dataclass(slots=True, frozen=True)
class AnalyticsRatingBucketMessage:
    rating: int
    count: int


@dataclass(slots=True, frozen=True)
class AnalyticsOperatorSnapshotMessage:
    operator_id: int
    display_name: str
    active_ticket_count: int
    closed_ticket_count: int
    average_first_response_time_seconds: int | None
    average_resolution_time_seconds: int | None
    average_satisfaction: float | None
    feedback_count: int


@dataclass(slots=True, frozen=True)
class AnalyticsCategorySnapshotMessage:
    category_id: int | None
    category_title: str
    created_ticket_count: int
    open_ticket_count: int
    closed_ticket_count: int
    average_satisfaction: float | None
    feedback_count: int
    sla_breach_count: int


@dataclass(slots=True, frozen=True)
class HelpdeskAnalyticsSnapshotMessage:
    window: str
    total_open_tickets: int
    queued_tickets_count: int
    assigned_tickets_count: int
    escalated_tickets_count: int
    closed_tickets_count: int
    tickets_per_operator: tuple[OperatorTicketLoadMessage, ...]
    period_created_tickets_count: int
    period_closed_tickets_count: int
    average_first_response_time_seconds: int | None
    average_resolution_time_seconds: int | None
    satisfaction_average: float | None
    feedback_count: int
    feedback_coverage_percent: int | None
    rating_distribution: tuple[AnalyticsRatingBucketMessage, ...]
    operator_snapshots: tuple[AnalyticsOperatorSnapshotMessage, ...]
    category_snapshots: tuple[AnalyticsCategorySnapshotMessage, ...]
    best_operators_by_closures: tuple[AnalyticsOperatorSnapshotMessage, ...]
    best_operators_by_satisfaction: tuple[AnalyticsOperatorSnapshotMessage, ...]
    top_categories: tuple[AnalyticsCategorySnapshotMessage, ...]
    first_response_breach_count: int
    resolution_breach_count: int
    sla_categories: tuple[AnalyticsCategorySnapshotMessage, ...]


@dataclass(slots=True, frozen=True)
class GetClientActiveTicketRequest:
    client_chat_id: int


@dataclass(slots=True, frozen=True)
class ListClientTicketCategoriesRequest:
    pass


@dataclass(slots=True, frozen=True)
class CreateTicketFromClientMessageRequest:
    command: ClientTicketMessageCommandMessage


@dataclass(slots=True, frozen=True)
class CreateTicketFromClientIntakeRequest:
    command: ClientTicketMessageCommandMessage


@dataclass(slots=True, frozen=True)
class GetTicketDetailsRequest:
    ticket_public_id: str
    actor: RequestActorMessage | None


@dataclass(slots=True, frozen=True)
class ListQueuedTicketsRequest:
    actor: RequestActorMessage | None


@dataclass(slots=True, frozen=True)
class ListOperatorTicketsRequest:
    operator_telegram_user_id: int
    actor: RequestActorMessage | None


@dataclass(slots=True, frozen=True)
class AssignNextQueuedTicketRequest:
    command: AssignNextQueuedTicketCommandMessage
    actor: RequestActorMessage | None


@dataclass(slots=True, frozen=True)
class AssignTicketToOperatorRequest:
    command: TicketAssignmentCommandMessage
    actor: RequestActorMessage | None


@dataclass(slots=True, frozen=True)
class CloseTicketRequest:
    ticket_public_id: str


@dataclass(slots=True, frozen=True)
class CloseTicketAsOperatorRequest:
    ticket_public_id: str
    actor: RequestActorMessage | None


@dataclass(slots=True, frozen=True)
class ReplyToTicketAsOperatorRequest:
    command: OperatorTicketReplyCommandMessage
    actor: RequestActorMessage | None


@dataclass(slots=True, frozen=True)
class ListMacrosRequest:
    actor: RequestActorMessage | None


@dataclass(slots=True, frozen=True)
class ApplyMacroToTicketRequest:
    command: ApplyMacroToTicketCommandMessage
    actor: RequestActorMessage | None


@dataclass(slots=True, frozen=True)
class ExportTicketReportRequest:
    ticket_public_id: str
    format: str
    actor: RequestActorMessage | None


@dataclass(slots=True, frozen=True)
class GetAnalyticsSnapshotRequest:
    window: str
    actor: RequestActorMessage | None
