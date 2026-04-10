from __future__ import annotations

from application.use_cases.tickets.summaries import TicketAttachmentSummary, TicketMessageSummary
from domain.enums.tickets import TicketAttachmentKind


def format_attachment_label(attachment: TicketAttachmentSummary) -> str:
    if attachment.kind == TicketAttachmentKind.PHOTO:
        return "Фото"
    if attachment.kind == TicketAttachmentKind.VOICE:
        return "Голосовое сообщение"
    if attachment.kind == TicketAttachmentKind.VIDEO:
        return "Видео"
    if attachment.filename:
        return f"Файл · {attachment.filename}"
    return "Файл"


def build_message_preview(
    *,
    text: str | None,
    attachment: TicketAttachmentSummary | None,
) -> str | None:
    normalized_text = _normalize_text(text)
    if attachment is None:
        return normalized_text
    if normalized_text:
        return f"{format_attachment_label(attachment)} — {normalized_text}"
    return format_attachment_label(attachment)


def format_history_body(message: TicketMessageSummary) -> str:
    preview = build_message_preview(text=message.text, attachment=message.attachment)
    return preview or "Сообщение без текста"


def _normalize_text(text: str | None) -> str | None:
    if text is None:
        return None
    normalized = " ".join(text.split())
    return normalized or None
