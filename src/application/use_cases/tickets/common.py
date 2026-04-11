from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

from application.use_cases.tickets.identifiers import format_public_ticket_number
from application.use_cases.tickets.summaries import TicketSummary
from domain.entities.ticket import Ticket, TicketAttachmentDetails, TicketDetails
from domain.enums.tickets import TicketEventType, TicketMessageSenderType, TicketStatus


def utcnow() -> datetime:
    return datetime.now(UTC)


def build_ticket_subject(message_text: str) -> str:
    first_line = (
        message_text.strip().splitlines()[0] if message_text.strip() else "Обращение клиента"
    )
    return first_line[:255]


def build_ticket_summary(
    ticket: Ticket | TicketDetails,
    *,
    created: bool = False,
    event_type: TicketEventType | None = None,
) -> TicketSummary:
    return TicketSummary(
        public_id=ticket.public_id,
        public_number=format_public_ticket_number(ticket.public_id),
        status=ticket.status,
        created=created,
        event_type=event_type,
    )


def build_status_payload(
    *,
    from_status: TicketStatus,
    to_status: TicketStatus,
    assigned_operator_id: int | None,
    previous_operator_id: int | None = None,
    actor_operator_id: int | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "from_status": from_status.value,
        "to_status": to_status.value,
    }
    if assigned_operator_id is not None:
        payload["assigned_operator_id"] = assigned_operator_id
    if previous_operator_id is not None:
        payload["previous_operator_id"] = previous_operator_id
    if actor_operator_id is not None:
        payload["actor_operator_id"] = actor_operator_id
    return payload


def build_message_payload(
    *,
    telegram_message_id: int,
    sender_type: TicketMessageSenderType,
    sender_operator_id: int | None,
    attachment: TicketAttachmentDetails | None = None,
    extra_payload: Mapping[str, object] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "telegram_message_id": telegram_message_id,
        "sender_type": sender_type.value,
    }
    if sender_operator_id is not None:
        payload["sender_operator_id"] = sender_operator_id
    if attachment is not None:
        payload.update(build_attachment_payload(attachment))
    if extra_payload is not None:
        payload.update(extra_payload)
    return payload


def build_event_type_for_message(
    sender_type: TicketMessageSenderType,
) -> TicketEventType | None:
    if sender_type == TicketMessageSenderType.CLIENT:
        return TicketEventType.CLIENT_MESSAGE_ADDED
    if sender_type == TicketMessageSenderType.OPERATOR:
        return TicketEventType.OPERATOR_MESSAGE_ADDED
    return None


def build_attachment_payload(attachment: TicketAttachmentDetails) -> dict[str, object]:
    payload: dict[str, object] = {
        "attachment_kind": attachment.kind.value,
        "attachment_file_id": attachment.telegram_file_id,
    }
    if attachment.telegram_file_unique_id is not None:
        payload["attachment_file_unique_id"] = attachment.telegram_file_unique_id
    if attachment.filename is not None:
        payload["attachment_filename"] = attachment.filename
    if attachment.mime_type is not None:
        payload["attachment_mime_type"] = attachment.mime_type
    if attachment.storage_path is not None:
        payload["attachment_storage_path"] = attachment.storage_path
    return payload
