from __future__ import annotations

from application.use_cases.tickets.message_content import (
    build_attachment_label as build_shared_attachment_label,
)
from application.use_cases.tickets.message_content import (
    build_message_preview as build_shared_message_preview,
)
from application.use_cases.tickets.summaries import TicketAttachmentSummary, TicketMessageSummary


def format_attachment_label(attachment: TicketAttachmentSummary) -> str:
    return build_shared_attachment_label(attachment)


def build_message_preview(
    *,
    text: str | None,
    attachment: TicketAttachmentSummary | None,
) -> str | None:
    return build_shared_message_preview(text=text, attachment=attachment)


def format_history_body(message: TicketMessageSummary) -> str:
    preview = build_message_preview(text=message.text, attachment=message.attachment)
    return preview or "Сообщение без текста"
