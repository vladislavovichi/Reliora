from __future__ import annotations

from typing import Protocol

from domain.enums.tickets import TicketAttachmentKind


class TicketAttachmentPreview(Protocol):
    kind: TicketAttachmentKind
    filename: str | None


def normalize_message_text(text: str | None) -> str | None:
    if text is None:
        return None
    normalized = " ".join(text.split())
    return normalized or None


def build_attachment_label(attachment: TicketAttachmentPreview) -> str:
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
    attachment: TicketAttachmentPreview | None,
) -> str | None:
    normalized_text = normalize_message_text(text)
    if attachment is None:
        return normalized_text
    if normalized_text:
        return f"{build_attachment_label(attachment)} — {normalized_text}"
    return build_attachment_label(attachment)


def build_ticket_subject(
    *,
    text: str | None,
    attachment: TicketAttachmentPreview | None,
) -> str:
    subject = build_message_preview(text=text, attachment=attachment) or "Обращение клиента"
    first_line = subject.strip().splitlines()[0] if subject.strip() else "Обращение клиента"
    return first_line[:255]


def build_ticket_mini_title(
    *,
    text: str | None,
    attachment: TicketAttachmentPreview | None,
    fallback: str,
) -> str:
    preview = build_message_preview(text=text, attachment=attachment)
    if preview is not None:
        return preview
    fallback_normalized = " ".join(fallback.split())
    return fallback_normalized or "Без описания"
