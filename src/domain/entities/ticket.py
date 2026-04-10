from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from domain.enums.tickets import (
    TicketAttachmentKind,
    TicketEventType,
    TicketMessageSenderType,
    TicketPriority,
    TicketStatus,
)


class Ticket(Protocol):
    """Ticket shape shared across the domain boundary."""

    id: int | None
    public_id: UUID
    client_chat_id: int
    status: TicketStatus
    priority: TicketPriority
    subject: str
    category_id: int | None
    assigned_operator_id: int | None
    created_at: datetime
    updated_at: datetime
    first_response_at: datetime | None
    closed_at: datetime | None


@dataclass(slots=True)
class TicketAttachmentDetails:
    kind: TicketAttachmentKind
    telegram_file_id: str
    telegram_file_unique_id: str | None
    filename: str | None
    mime_type: str | None
    storage_path: str | None = None


@dataclass(slots=True)
class TicketMessageDetails:
    telegram_message_id: int
    sender_type: TicketMessageSenderType
    sender_operator_id: int | None
    sender_operator_name: str | None
    text: str | None
    created_at: datetime
    attachment: TicketAttachmentDetails | None = None


@dataclass(slots=True)
class TicketEventDetails:
    event_type: TicketEventType
    payload_json: dict[str, object] | None
    created_at: datetime


@dataclass(slots=True)
class TicketInternalNoteDetails:
    id: int
    author_operator_id: int
    author_operator_name: str | None
    text: str
    created_at: datetime


@dataclass(slots=True)
class TicketDetails:
    id: int
    public_id: UUID
    client_chat_id: int
    status: TicketStatus
    priority: TicketPriority
    subject: str
    assigned_operator_id: int | None
    assigned_operator_name: str | None
    assigned_operator_telegram_user_id: int | None
    created_at: datetime
    updated_at: datetime
    first_response_at: datetime | None
    closed_at: datetime | None
    category_id: int | None = None
    category_code: str | None = None
    category_title: str | None = None
    tags: tuple[str, ...] = ()
    last_message_text: str | None = None
    last_message_sender_type: TicketMessageSenderType | None = None
    last_message_attachment: TicketAttachmentDetails | None = None
    message_history: tuple[TicketMessageDetails, ...] = ()
    internal_notes: tuple[TicketInternalNoteDetails, ...] = ()
