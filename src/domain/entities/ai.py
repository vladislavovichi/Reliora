from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class TicketAISummaryDetails:
    ticket_id: int
    short_summary: str
    user_goal: str
    actions_taken: str
    current_status: str
    generated_at: datetime
    source_ticket_updated_at: datetime
    source_message_count: int
    source_internal_note_count: int
    model_id: str | None = None
