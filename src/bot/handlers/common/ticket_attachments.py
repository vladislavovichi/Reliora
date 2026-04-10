from __future__ import annotations

from dataclasses import dataclass

from aiogram import Bot
from aiogram.types import Message

from domain.entities.ticket import TicketAttachmentDetails
from domain.enums.tickets import TicketAttachmentKind
from infrastructure.assets.storage import LocalTicketAssetStorage
from infrastructure.config.settings import get_settings


@dataclass(slots=True, frozen=True)
class IncomingTicketContent:
    text: str | None
    attachment: TicketAttachmentDetails | None


async def extract_ticket_content(
    message: Message,
    *,
    bot: Bot,
) -> IncomingTicketContent | None:
    text = _normalize_text(message.text or message.caption)
    if message.photo:
        photo = message.photo[-1]
        return IncomingTicketContent(
            text=text,
            attachment=await _store_attachment(
                bot,
                TicketAttachmentDetails(
                    kind=TicketAttachmentKind.PHOTO,
                    telegram_file_id=photo.file_id,
                    telegram_file_unique_id=photo.file_unique_id,
                    filename=None,
                    mime_type=None,
                ),
            ),
        )
    if message.document is not None:
        document = message.document
        return IncomingTicketContent(
            text=text,
            attachment=await _store_attachment(
                bot,
                TicketAttachmentDetails(
                    kind=TicketAttachmentKind.DOCUMENT,
                    telegram_file_id=document.file_id,
                    telegram_file_unique_id=document.file_unique_id,
                    filename=document.file_name,
                    mime_type=document.mime_type,
                ),
            ),
        )
    if message.voice is not None:
        voice = message.voice
        return IncomingTicketContent(
            text=text,
            attachment=await _store_attachment(
                bot,
                TicketAttachmentDetails(
                    kind=TicketAttachmentKind.VOICE,
                    telegram_file_id=voice.file_id,
                    telegram_file_unique_id=voice.file_unique_id,
                    filename=None,
                    mime_type=voice.mime_type,
                ),
            ),
        )
    if message.video is not None:
        video = message.video
        return IncomingTicketContent(
            text=text,
            attachment=await _store_attachment(
                bot,
                TicketAttachmentDetails(
                    kind=TicketAttachmentKind.VIDEO,
                    telegram_file_id=video.file_id,
                    telegram_file_unique_id=video.file_unique_id,
                    filename=video.file_name,
                    mime_type=video.mime_type,
                ),
            ),
        )
    if text is not None:
        return IncomingTicketContent(text=text, attachment=None)
    return None


def _normalize_text(text: str | None) -> str | None:
    if text is None:
        return None
    normalized = text.strip()
    return normalized or None


async def _store_attachment(
    bot: Bot,
    attachment: TicketAttachmentDetails,
) -> TicketAttachmentDetails:
    storage = LocalTicketAssetStorage(get_settings().assets.path)
    return await storage.save_telegram_attachment(bot, attachment=attachment)
