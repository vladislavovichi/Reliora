from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from aiogram import Bot

from domain.entities.ticket import TicketAttachmentDetails
from domain.enums.tickets import TicketAttachmentKind


class LocalTicketAssetStorage:
    def __init__(self, base_path: Path) -> None:
        self.base_path = base_path

    async def save_telegram_attachment(
        self,
        bot: Bot,
        *,
        attachment: TicketAttachmentDetails,
    ) -> TicketAttachmentDetails:
        relative_path = self._build_relative_path(attachment)
        absolute_path = self.base_path / relative_path
        absolute_path.parent.mkdir(parents=True, exist_ok=True)

        if not absolute_path.exists():
            await bot.download(attachment.telegram_file_id, destination=absolute_path)

        return TicketAttachmentDetails(
            kind=attachment.kind,
            telegram_file_id=attachment.telegram_file_id,
            telegram_file_unique_id=attachment.telegram_file_unique_id,
            filename=attachment.filename,
            mime_type=attachment.mime_type,
            storage_path=relative_path.as_posix(),
        )

    def resolve_path(self, relative_path: str) -> Path:
        return self._resolve_safe_relative_path(relative_path)

    def _build_relative_path(self, attachment: TicketAttachmentDetails) -> Path:
        suffix = self._resolve_suffix(attachment)
        unique_name = attachment.telegram_file_unique_id or uuid4().hex
        filename = f"{unique_name}{suffix}"
        return Path(attachment.kind.value) / filename

    def _resolve_suffix(self, attachment: TicketAttachmentDetails) -> str:
        if attachment.filename:
            suffix = Path(attachment.filename).suffix.strip()
            if suffix:
                return suffix

        kind_suffixes = {
            TicketAttachmentKind.PHOTO: ".jpg",
            TicketAttachmentKind.DOCUMENT: ".bin",
            TicketAttachmentKind.VOICE: ".ogg",
            TicketAttachmentKind.VIDEO: ".mp4",
        }
        return kind_suffixes.get(attachment.kind, ".bin")

    def _resolve_safe_relative_path(self, relative_path: str) -> Path:
        candidate = Path(relative_path)
        if candidate.is_absolute():
            raise ValueError("absolute storage paths are not allowed")
        if any(part in {"..", ""} for part in candidate.parts):
            raise ValueError("unsafe storage path")

        resolved = (self.base_path / candidate).resolve()
        base_resolved = self.base_path.resolve()
        if base_resolved == resolved or base_resolved in resolved.parents:
            return resolved
        raise ValueError("storage path escapes asset root")
