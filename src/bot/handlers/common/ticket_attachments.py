from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from aiogram import Bot
from aiogram.types import Message

from bot.texts.common import (
    ATTACHMENT_NOT_SUPPORTED_TEXT,
    ATTACHMENT_TOO_LARGE_TEXT,
    ATTACHMENT_UNSAFE_TEXT,
)
from domain.entities.ticket import TicketAttachmentDetails
from domain.enums.tickets import TicketAttachmentKind
from infrastructure.assets.storage import LocalTicketAssetStorage
from infrastructure.config.settings import AttachmentLimitsConfig, get_settings

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class IncomingTicketContent:
    text: str | None
    attachment: TicketAttachmentDetails | None


class AttachmentRejectedError(ValueError):
    """Raised when the attachment does not match the accepted inbound policy."""


async def extract_ticket_content(
    message: Message,
    *,
    bot: Bot,
) -> IncomingTicketContent | None:
    settings = get_settings()
    text = _normalize_text(message.text or message.caption)
    if message.photo:
        photo = message.photo[-1]
        _ensure_size_allowed(
            kind=TicketAttachmentKind.PHOTO,
            size_bytes=photo.file_size,
            limits=settings.attachments,
        )
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
        _ensure_size_allowed(
            kind=TicketAttachmentKind.DOCUMENT,
            size_bytes=document.file_size,
            limits=settings.attachments,
        )
        _ensure_document_is_safe(
            filename=document.file_name,
            mime_type=document.mime_type,
            limits=settings.attachments,
        )
        return IncomingTicketContent(
            text=text,
            attachment=await _store_attachment(
                bot,
                TicketAttachmentDetails(
                    kind=TicketAttachmentKind.DOCUMENT,
                    telegram_file_id=document.file_id,
                    telegram_file_unique_id=document.file_unique_id,
                    filename=_normalize_filename(document.file_name),
                    mime_type=_normalize_mime_type(document.mime_type),
                ),
            ),
        )
    if message.voice is not None:
        voice = message.voice
        _ensure_size_allowed(
            kind=TicketAttachmentKind.VOICE,
            size_bytes=voice.file_size,
            limits=settings.attachments,
        )
        return IncomingTicketContent(
            text=text,
            attachment=await _store_attachment(
                bot,
                TicketAttachmentDetails(
                    kind=TicketAttachmentKind.VOICE,
                    telegram_file_id=voice.file_id,
                    telegram_file_unique_id=voice.file_unique_id,
                    filename=None,
                    mime_type=_normalize_mime_type(voice.mime_type),
                ),
            ),
        )
    if message.video is not None:
        video = message.video
        _ensure_size_allowed(
            kind=TicketAttachmentKind.VIDEO,
            size_bytes=video.file_size,
            limits=settings.attachments,
        )
        return IncomingTicketContent(
            text=text,
            attachment=await _store_attachment(
                bot,
                TicketAttachmentDetails(
                    kind=TicketAttachmentKind.VIDEO,
                    telegram_file_id=video.file_id,
                    telegram_file_unique_id=video.file_unique_id,
                    filename=_normalize_filename(video.file_name),
                    mime_type=_normalize_mime_type(video.mime_type),
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
    stored = await storage.save_telegram_attachment(bot, attachment=attachment)
    logger.info(
        "Attachment accepted kind=%s file_unique_id=%s storage_path=%s",
        stored.kind.value,
        stored.telegram_file_unique_id,
        stored.storage_path,
    )
    return stored


def _ensure_size_allowed(
    *,
    kind: TicketAttachmentKind,
    size_bytes: int | None,
    limits: AttachmentLimitsConfig,
) -> None:
    if size_bytes is None:
        return
    max_bytes = {
        TicketAttachmentKind.PHOTO: limits.photo_max_bytes,
        TicketAttachmentKind.DOCUMENT: limits.document_max_bytes,
        TicketAttachmentKind.VOICE: limits.voice_max_bytes,
        TicketAttachmentKind.VIDEO: limits.video_max_bytes,
    }.get(kind)
    if max_bytes is None:
        raise AttachmentRejectedError(ATTACHMENT_NOT_SUPPORTED_TEXT)
    if size_bytes > max_bytes:
        logger.warning(
            "Attachment rejected by size kind=%s size_bytes=%s limit_bytes=%s",
            kind.value,
            size_bytes,
            max_bytes,
        )
        raise AttachmentRejectedError(ATTACHMENT_TOO_LARGE_TEXT)


def _ensure_document_is_safe(
    *,
    filename: str | None,
    mime_type: str | None,
    limits: AttachmentLimitsConfig,
) -> None:
    normalized_mime_type = _normalize_mime_type(mime_type)
    if normalized_mime_type in limits.blocked_document_mime_types:
        logger.warning("Attachment rejected by mime_type mime_type=%s", normalized_mime_type)
        raise AttachmentRejectedError(ATTACHMENT_UNSAFE_TEXT)
    if not filename:
        return
    suffix = Path(filename).suffix.lower()
    if suffix in limits.blocked_document_extensions:
        logger.warning("Attachment rejected by extension filename=%s", filename)
        raise AttachmentRejectedError(ATTACHMENT_UNSAFE_TEXT)


def _normalize_filename(filename: str | None) -> str | None:
    if filename is None:
        return None
    normalized = Path(filename).name.strip()
    if not normalized:
        return None
    normalized = re.sub(r"\s+", " ", normalized)
    if len(normalized) > 128:
        stem = Path(normalized).stem[:96].rstrip()
        suffix = Path(normalized).suffix[:16]
        normalized = f"{stem}{suffix}" if stem else normalized[:128]
    return normalized


def _normalize_mime_type(mime_type: str | None) -> str | None:
    if mime_type is None:
        return None
    normalized = mime_type.strip().lower()
    if not normalized:
        return None
    return normalized[:128]
