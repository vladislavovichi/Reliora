from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from application.use_cases.tickets.identifiers import format_public_ticket_number
from domain.contracts.repositories import (
    TicketEventRepository,
    TicketFeedbackRepository,
    TicketRepository,
)
from domain.entities.feedback import TicketFeedback
from domain.entities.ticket import (
    TicketAttachmentDetails,
    TicketDetails,
    TicketEventDetails,
)
from domain.enums.tickets import (
    TicketAttachmentKind,
    TicketEventType,
    TicketMessageSenderType,
    TicketStatus,
)


class TicketReportFormat(StrEnum):
    CSV = "csv"
    HTML = "html"


@dataclass(slots=True, frozen=True)
class TicketReportFeedback:
    rating: int
    comment: str | None
    submitted_at: datetime


@dataclass(slots=True, frozen=True)
class TicketReportAttachment:
    kind: TicketAttachmentKind
    telegram_file_id: str
    telegram_file_unique_id: str | None
    filename: str | None
    mime_type: str | None
    storage_path: str | None = None


@dataclass(slots=True, frozen=True)
class TicketReportMessage:
    sender_type: TicketMessageSenderType
    sender_operator_name: str | None
    text: str | None
    created_at: datetime
    attachment: TicketReportAttachment | None = None


@dataclass(slots=True, frozen=True)
class TicketReportEvent:
    event_type: TicketEventType
    payload_json: Mapping[str, object] | None
    created_at: datetime


@dataclass(slots=True, frozen=True)
class TicketReportInternalNote:
    author_operator_id: int
    author_operator_name: str | None
    text: str
    created_at: datetime


@dataclass(slots=True, frozen=True)
class TicketReport:
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
    updated_at: datetime
    first_response_at: datetime | None
    first_response_seconds: int | None
    closed_at: datetime | None
    category_code: str | None
    category_title: str | None
    tags: tuple[str, ...]
    feedback: TicketReportFeedback | None
    messages: tuple[TicketReportMessage, ...]
    events: tuple[TicketReportEvent, ...]
    assigned_operator_username: str | None = None
    internal_notes: tuple[TicketReportInternalNote, ...] = ()


@dataclass(slots=True, frozen=True)
class TicketReportExport:
    format: TicketReportFormat
    filename: str
    content_type: str
    content: bytes
    report: TicketReport


TicketReportRenderer = Callable[[TicketReport], bytes]


class ExportTicketReportUseCase:
    def __init__(
        self,
        *,
        ticket_repository: TicketRepository,
        ticket_feedback_repository: TicketFeedbackRepository,
        ticket_event_repository: TicketEventRepository,
        csv_renderer: TicketReportRenderer,
        html_renderer: TicketReportRenderer,
        include_internal_notes: bool = True,
    ) -> None:
        self.ticket_repository = ticket_repository
        self.ticket_feedback_repository = ticket_feedback_repository
        self.ticket_event_repository = ticket_event_repository
        self.csv_renderer = csv_renderer
        self.html_renderer = html_renderer
        self.include_internal_notes = include_internal_notes

    async def __call__(
        self,
        *,
        ticket_public_id: UUID,
        format: TicketReportFormat,
    ) -> TicketReportExport | None:
        ticket = await self.ticket_repository.get_details_by_public_id(ticket_public_id)
        if ticket is None:
            return None

        feedback = await self.ticket_feedback_repository.get_by_ticket_id(ticket_id=ticket.id)
        events = await self.ticket_event_repository.list_for_ticket(ticket_id=ticket.id)
        report = build_ticket_report(
            ticket=ticket,
            feedback=feedback,
            events=events,
            include_internal_notes=self.include_internal_notes,
        )

        if format == TicketReportFormat.CSV:
            return TicketReportExport(
                format=format,
                filename=_build_filename(report.public_number, extension="csv"),
                content_type="text/csv",
                content=self.csv_renderer(report),
                report=report,
            )

        return TicketReportExport(
            format=format,
            filename=_build_filename(report.public_number, extension="html"),
            content_type="text/html",
            content=self.html_renderer(report),
            report=report,
        )


def build_ticket_report(
    *,
    ticket: TicketDetails,
    feedback: TicketFeedback | None,
    events: Sequence[TicketEventDetails],
    include_internal_notes: bool = True,
) -> TicketReport:
    first_response_seconds: int | None = None
    if ticket.first_response_at is not None:
        first_response_seconds = int(
            max((ticket.first_response_at - ticket.created_at).total_seconds(), 0)
        )

    return TicketReport(
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
        updated_at=ticket.updated_at,
        first_response_at=ticket.first_response_at,
        first_response_seconds=first_response_seconds,
        closed_at=ticket.closed_at,
        category_code=ticket.category_code,
        category_title=ticket.category_title,
        tags=ticket.tags,
        feedback=(
            TicketReportFeedback(
                rating=feedback.rating,
                comment=feedback.comment,
                submitted_at=feedback.submitted_at,
            )
            if feedback is not None
            else None
        ),
        messages=tuple(
            TicketReportMessage(
                sender_type=message.sender_type,
                sender_operator_name=message.sender_operator_name,
                text=message.text,
                attachment=(
                    build_ticket_report_attachment(message.attachment)
                    if message.attachment is not None
                    else None
                ),
                created_at=message.created_at,
            )
            for message in ticket.message_history
        ),
        internal_notes=tuple(
            TicketReportInternalNote(
                author_operator_id=note.author_operator_id,
                author_operator_name=note.author_operator_name,
                text=note.text,
                created_at=note.created_at,
            )
            for note in ticket.internal_notes
        )
        if include_internal_notes
        else (),
        events=tuple(
            TicketReportEvent(
                event_type=event.event_type,
                payload_json=event.payload_json,
                created_at=event.created_at,
            )
            for event in events
            if _is_relevant_event(event.event_type)
        ),
    )


def build_ticket_report_attachment(
    attachment: TicketAttachmentDetails,
) -> TicketReportAttachment:
    return TicketReportAttachment(
        kind=attachment.kind,
        telegram_file_id=attachment.telegram_file_id,
        telegram_file_unique_id=attachment.telegram_file_unique_id,
        filename=attachment.filename,
        mime_type=attachment.mime_type,
        storage_path=attachment.storage_path,
    )


def _build_filename(public_number: str, *, extension: str) -> str:
    normalized = public_number.strip().lower().replace(" ", "-")
    return f"ticket-report-{normalized}.{extension}"


def _is_relevant_event(event_type: TicketEventType) -> bool:
    return event_type in {
        TicketEventType.CREATED,
        TicketEventType.QUEUED,
        TicketEventType.ASSIGNED,
        TicketEventType.REASSIGNED,
        TicketEventType.AUTO_REASSIGNED,
        TicketEventType.ESCALATED,
        TicketEventType.AUTO_ESCALATED,
        TicketEventType.SLA_BREACHED_FIRST_RESPONSE,
        TicketEventType.SLA_BREACHED_RESOLUTION,
        TicketEventType.TAG_ADDED,
        TicketEventType.TAG_REMOVED,
        TicketEventType.CLOSED,
    }
