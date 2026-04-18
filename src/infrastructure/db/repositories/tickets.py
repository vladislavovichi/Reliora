from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.ticket import (
    TicketAttachmentDetails,
    TicketEventDetails,
    TicketInternalNoteDetails,
    TicketMessageDetails,
)
from domain.enums.tickets import (
    TicketEventType,
    TicketMessageSenderType,
    TicketSentiment,
    TicketSignalConfidence,
)
from infrastructure.db.models.ticket import TicketEvent, TicketInternalNote, TicketMessage
from infrastructure.db.repositories.ticket_message_mapping import build_ticket_message_details
from infrastructure.db.repositories.ticket_metrics import SqlAlchemyTicketMetricsRepository
from infrastructure.db.repositories.ticket_reads import SqlAlchemyTicketReadRepository
from infrastructure.db.repositories.ticket_writes import SqlAlchemyTicketWriteRepository


class SqlAlchemyTicketRepository(
    SqlAlchemyTicketWriteRepository,
    SqlAlchemyTicketReadRepository,
    SqlAlchemyTicketMetricsRepository,
):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session


class SqlAlchemyTicketMessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(
        self,
        *,
        ticket_id: int,
        telegram_message_id: int,
        sender_type: TicketMessageSenderType,
        text: str | None,
        attachment: TicketAttachmentDetails | None = None,
        sender_operator_id: int | None = None,
        sentiment: TicketSentiment | None = None,
        sentiment_confidence: TicketSignalConfidence | None = None,
        sentiment_reason: str | None = None,
    ) -> None:
        ticket_message = TicketMessage(
            ticket_id=ticket_id,
            telegram_message_id=telegram_message_id,
            sender_type=sender_type,
            sender_operator_id=sender_operator_id,
            text=text,
            attachment_kind=attachment.kind if attachment is not None else None,
            attachment_file_id=attachment.telegram_file_id if attachment is not None else None,
            attachment_file_unique_id=(
                attachment.telegram_file_unique_id if attachment is not None else None
            ),
            attachment_filename=attachment.filename if attachment is not None else None,
            attachment_mime_type=attachment.mime_type if attachment is not None else None,
            attachment_storage_path=attachment.storage_path if attachment is not None else None,
            sentiment=sentiment,
            sentiment_confidence=sentiment_confidence,
            sentiment_reason=sentiment_reason,
        )
        self.session.add(ticket_message)
        await self.session.flush()

    async def list_recent_for_ticket(
        self,
        *,
        ticket_id: int,
        limit: int = 6,
    ) -> tuple[TicketMessageDetails, ...]:
        from sqlalchemy import desc

        from infrastructure.db.models.operator import Operator

        statement = (
            select(TicketMessage, Operator.display_name)
            .join(Operator, TicketMessage.sender_operator_id == Operator.id, isouter=True)
            .where(TicketMessage.ticket_id == ticket_id)
            .order_by(desc(TicketMessage.created_at), desc(TicketMessage.id))
            .limit(limit)
        )
        result = await self.session.execute(statement)
        rows = list(reversed(result.all()))
        return tuple(
            build_ticket_message_details(
                message,
                sender_operator_name=sender_operator_name,
            )
            for message, sender_operator_name in rows
        )

    async def mark_duplicate(
        self,
        *,
        ticket_id: int,
        telegram_message_id: int,
        occurred_at: datetime,
    ) -> None:
        statement = select(TicketMessage).where(
            TicketMessage.ticket_id == ticket_id,
            TicketMessage.telegram_message_id == telegram_message_id,
            TicketMessage.sender_type == TicketMessageSenderType.CLIENT,
        )
        result = await self.session.execute(statement)
        ticket_message = result.scalar_one_or_none()
        if ticket_message is None:
            raise RuntimeError("Не найдено каноническое сообщение для объединения дублей.")
        ticket_message.duplicate_count += 1
        ticket_message.last_duplicate_at = occurred_at
        await self.session.flush()

    async def allocate_internal_telegram_message_id(
        self,
        *,
        ticket_id: int,
        sender_type: TicketMessageSenderType,
    ) -> int:
        statement = select(func.min(TicketMessage.telegram_message_id)).where(
            TicketMessage.ticket_id == ticket_id,
            TicketMessage.sender_type == sender_type,
        )
        result = await self.session.execute(statement)
        current_min = result.scalar_one_or_none()
        if current_min is None or current_min >= 0:
            return -1
        return int(current_min) - 1


class SqlAlchemyTicketInternalNoteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(
        self,
        *,
        ticket_id: int,
        author_operator_id: int,
        text: str,
    ) -> TicketInternalNoteDetails:
        note = TicketInternalNote(
            ticket_id=ticket_id,
            author_operator_id=author_operator_id,
            text=text,
        )
        self.session.add(note)
        await self.session.flush()

        return TicketInternalNoteDetails(
            id=note.id,
            author_operator_id=note.author_operator_id,
            author_operator_name=None,
            text=note.text,
            created_at=note.created_at,
        )


class SqlAlchemyTicketEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(
        self,
        *,
        ticket_id: int,
        event_type: TicketEventType,
        payload_json: Mapping[str, object] | None = None,
    ) -> None:
        ticket_event = TicketEvent(
            ticket_id=ticket_id,
            event_type=event_type,
            payload_json=dict(payload_json) if payload_json is not None else None,
        )
        self.session.add(ticket_event)
        await self.session.flush()

    async def exists(self, *, ticket_id: int, event_type: TicketEventType) -> bool:
        statement = (
            select(TicketEvent.id)
            .where(TicketEvent.ticket_id == ticket_id, TicketEvent.event_type == event_type)
            .limit(1)
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none() is not None

    async def list_for_ticket(self, *, ticket_id: int) -> tuple[TicketEventDetails, ...]:
        statement = (
            select(TicketEvent.event_type, TicketEvent.payload_json, TicketEvent.created_at)
            .where(TicketEvent.ticket_id == ticket_id)
            .order_by(TicketEvent.created_at.asc(), TicketEvent.id.asc())
        )
        result = await self.session.execute(statement)
        return tuple(
            TicketEventDetails(
                event_type=event_type,
                payload_json=payload_json,
                created_at=created_at,
            )
            for event_type, payload_json, created_at in result.all()
        )
