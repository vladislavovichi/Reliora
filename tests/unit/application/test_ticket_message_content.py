from __future__ import annotations

from application.use_cases.tickets.message_content import (
    build_message_preview,
    build_ticket_mini_title,
    build_ticket_subject,
)
from domain.entities.ticket import TicketAttachmentDetails
from domain.enums.tickets import TicketAttachmentKind


def test_build_ticket_subject_uses_attachment_when_text_missing() -> None:
    attachment = TicketAttachmentDetails(
        kind=TicketAttachmentKind.PHOTO,
        telegram_file_id="photo-1",
        telegram_file_unique_id="photo-unique-1",
        filename=None,
        mime_type="image/jpeg",
        storage_path="photo/photo-unique-1.jpg",
    )

    result = build_ticket_subject(text=None, attachment=attachment)

    assert result == "Фото"


def test_build_ticket_subject_keeps_attachment_context_for_captioned_media() -> None:
    attachment = TicketAttachmentDetails(
        kind=TicketAttachmentKind.DOCUMENT,
        telegram_file_id="file-1",
        telegram_file_unique_id="file-unique-1",
        filename="guide.pdf",
        mime_type="application/pdf",
        storage_path="document/file-unique-1.pdf",
    )

    result = build_ticket_subject(text="Смотрите вложение", attachment=attachment)

    assert result == "Файл · guide.pdf — Смотрите вложение"


def test_build_ticket_mini_title_uses_first_attachment_preview() -> None:
    attachment = TicketAttachmentDetails(
        kind=TicketAttachmentKind.VOICE,
        telegram_file_id="voice-1",
        telegram_file_unique_id="voice-unique-1",
        filename=None,
        mime_type="audio/ogg",
        storage_path="voice/voice-unique-1.ogg",
    )

    result = build_ticket_mini_title(
        text=None,
        attachment=attachment,
        fallback="Обращение клиента",
    )

    assert result == "Голосовое сообщение"


def test_build_message_preview_returns_none_for_empty_payload() -> None:
    assert build_message_preview(text="   ", attachment=None) is None
