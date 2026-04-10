from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aiogram.fsm.context import FSMContext

from bot.handlers.common.ticket_attachments import IncomingTicketContent
from domain.entities.ticket import TicketAttachmentDetails
from domain.enums.tickets import TicketAttachmentKind

INTAKE_DRAFT_KEY = "draft"


@dataclass(slots=True, frozen=True)
class PendingClientIntakeDraft:
    client_chat_id: int
    telegram_message_id: int
    text: str | None
    attachment: TicketAttachmentDetails | None

    @property
    def has_meaningful_text(self) -> bool:
        return self.text is not None

    def to_content(self) -> IncomingTicketContent:
        return IncomingTicketContent(text=self.text, attachment=self.attachment)


async def store_pending_client_intake_draft(
    *,
    state: FSMContext,
    draft: PendingClientIntakeDraft,
    extra_data: dict[str, object] | None = None,
) -> None:
    payload: dict[str, object] = dict(extra_data or {})
    payload[INTAKE_DRAFT_KEY] = serialize_pending_client_intake_draft(draft)
    await state.set_data(payload)


def load_pending_client_intake_draft(state_data: dict[str, Any]) -> PendingClientIntakeDraft | None:
    raw = state_data.get(INTAKE_DRAFT_KEY)
    if not isinstance(raw, dict):
        return None

    client_chat_id = raw.get("client_chat_id")
    telegram_message_id = raw.get("telegram_message_id")
    if not isinstance(client_chat_id, int) or not isinstance(telegram_message_id, int):
        return None

    attachment = _deserialize_attachment(raw.get("attachment"))
    text = raw.get("text")
    normalized_text = text if isinstance(text, str) and text else None
    return PendingClientIntakeDraft(
        client_chat_id=client_chat_id,
        telegram_message_id=telegram_message_id,
        text=normalized_text,
        attachment=attachment,
    )


def serialize_pending_client_intake_draft(
    draft: PendingClientIntakeDraft,
) -> dict[str, object]:
    return {
        "client_chat_id": draft.client_chat_id,
        "telegram_message_id": draft.telegram_message_id,
        "text": draft.text,
        "attachment": _serialize_attachment(draft.attachment),
    }


def build_pending_client_intake_draft(
    *,
    client_chat_id: int,
    telegram_message_id: int,
    content: IncomingTicketContent,
) -> PendingClientIntakeDraft:
    return PendingClientIntakeDraft(
        client_chat_id=client_chat_id,
        telegram_message_id=telegram_message_id,
        text=content.text,
        attachment=content.attachment,
    )


def _serialize_attachment(
    attachment: TicketAttachmentDetails | None,
) -> dict[str, object] | None:
    if attachment is None:
        return None
    return {
        "kind": attachment.kind.value,
        "telegram_file_id": attachment.telegram_file_id,
        "telegram_file_unique_id": attachment.telegram_file_unique_id,
        "filename": attachment.filename,
        "mime_type": attachment.mime_type,
        "storage_path": attachment.storage_path,
    }


def _deserialize_attachment(value: object) -> TicketAttachmentDetails | None:
    if not isinstance(value, dict):
        return None

    kind = value.get("kind")
    telegram_file_id = value.get("telegram_file_id")
    if not isinstance(kind, str) or not isinstance(telegram_file_id, str):
        return None

    telegram_file_unique_id = value.get("telegram_file_unique_id")
    filename = value.get("filename")
    mime_type = value.get("mime_type")
    storage_path = value.get("storage_path")
    return TicketAttachmentDetails(
        kind=TicketAttachmentKind(kind),
        telegram_file_id=telegram_file_id,
        telegram_file_unique_id=(
            telegram_file_unique_id if isinstance(telegram_file_unique_id, str) else None
        ),
        filename=filename if isinstance(filename, str) else None,
        mime_type=mime_type if isinstance(mime_type, str) else None,
        storage_path=storage_path if isinstance(storage_path, str) else None,
    )
