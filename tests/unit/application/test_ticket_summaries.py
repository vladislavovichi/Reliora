from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from application.use_cases.tickets.summaries import build_historical_ticket_summary
from domain.entities.ticket import TicketAttachmentDetails, TicketHistoryEntry
from domain.enums.tickets import TicketAttachmentKind, TicketStatus


def test_build_historical_ticket_summary_keeps_first_media_preview() -> None:
    entry = TicketHistoryEntry(
        public_id=uuid4(),
        status=TicketStatus.CLOSED,
        subject="Обращение клиента",
        created_at=datetime(2026, 4, 8, 12, 0, tzinfo=UTC),
        closed_at=datetime(2026, 4, 8, 13, 0, tzinfo=UTC),
        category_id=2,
        category_code="access",
        category_title="Доступ и вход",
        first_client_message_text=None,
        first_client_message_attachment=TicketAttachmentDetails(
            kind=TicketAttachmentKind.VIDEO,
            telegram_file_id="video-1",
            telegram_file_unique_id="video-unique-1",
            filename="issue.mp4",
            mime_type="video/mp4",
            storage_path="video/video-unique-1.mp4",
        ),
    )

    summary = build_historical_ticket_summary(entry)

    assert summary.mini_title == "Видео"
