from __future__ import annotations

from datetime import datetime
from typing import Protocol


class TicketFeedback(Protocol):
    """Ticket feedback shape shared across the domain boundary."""

    id: int | None
    ticket_id: int
    client_chat_id: int
    rating: int
    comment: str | None
    submitted_at: datetime
