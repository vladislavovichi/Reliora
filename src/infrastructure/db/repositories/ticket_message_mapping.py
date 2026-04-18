from __future__ import annotations

from domain.entities.ticket import TicketAttachmentDetails, TicketMessageDetails
from domain.enums.tickets import TicketAttachmentKind
from infrastructure.db.models.ticket import TicketMessage


def build_attachment_details(
    *,
    kind: TicketAttachmentKind | None,
    file_id: str | None,
    file_unique_id: str | None,
    filename: str | None,
    mime_type: str | None,
    storage_path: str | None,
) -> TicketAttachmentDetails | None:
    if kind is None or file_id is None:
        return None
    return TicketAttachmentDetails(
        kind=kind,
        telegram_file_id=file_id,
        telegram_file_unique_id=file_unique_id,
        filename=filename,
        mime_type=mime_type,
        storage_path=storage_path,
    )


def build_attachment_from_message(
    message: TicketMessage,
) -> TicketAttachmentDetails | None:
    return build_attachment_details(
        kind=message.attachment_kind,
        file_id=message.attachment_file_id,
        file_unique_id=message.attachment_file_unique_id,
        filename=message.attachment_filename,
        mime_type=message.attachment_mime_type,
        storage_path=message.attachment_storage_path,
    )


def build_ticket_message_details(
    message: TicketMessage,
    *,
    sender_operator_name: str | None,
) -> TicketMessageDetails:
    return TicketMessageDetails(
        telegram_message_id=message.telegram_message_id,
        sender_type=message.sender_type,
        sender_operator_id=message.sender_operator_id,
        sender_operator_name=sender_operator_name,
        text=message.text,
        attachment=build_attachment_from_message(message),
        sentiment=message.sentiment,
        sentiment_confidence=message.sentiment_confidence,
        sentiment_reason=message.sentiment_reason,
        duplicate_count=message.duplicate_count,
        last_duplicate_at=message.last_duplicate_at,
        created_at=message.created_at,
    )
