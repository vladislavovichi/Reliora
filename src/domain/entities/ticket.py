from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from domain.enums.tickets import TicketPriority, TicketStatus


@dataclass(slots=True, kw_only=True)
class Ticket:
    client_telegram_id: int
    subject: str
    id: UUID = field(default_factory=uuid4)
    status: TicketStatus = TicketStatus.NEW
    priority: TicketPriority = TicketPriority.NORMAL
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
