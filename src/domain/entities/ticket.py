from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from domain.enums.tickets import TicketMessageSenderType, TicketPriority, TicketStatus


class Ticket(Protocol):
    """Ticket shape shared across the domain boundary."""

    id: int | None
    public_id: UUID
    client_chat_id: int
    status: TicketStatus
    priority: TicketPriority
    subject: str
    assigned_operator_id: int | None
    created_at: datetime
    updated_at: datetime
    first_response_at: datetime | None
    closed_at: datetime | None


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
    created_at: datetime
    updated_at: datetime
    first_response_at: datetime | None
    closed_at: datetime | None
    last_message_text: str | None = None
    last_message_sender_type: TicketMessageSenderType | None = None
