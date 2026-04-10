from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.ticket import TicketEventDetails
from domain.enums.tickets import TicketEventType, TicketMessageSenderType
from infrastructure.db.models.ticket import TicketEvent, TicketMessage
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
        text: str,
        sender_operator_id: int | None = None,
    ) -> None:
        ticket_message = TicketMessage(
            ticket_id=ticket_id,
            telegram_message_id=telegram_message_id,
            sender_type=sender_type,
            sender_operator_id=sender_operator_id,
            text=text,
        )
        self.session.add(ticket_message)
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
        return cast(object | None, result.scalar_one_or_none()) is not None

    async def list_for_ticket(self, *, ticket_id: int) -> tuple[TicketEventDetails, ...]:
        statement = (
            select(TicketEvent.event_type, TicketEvent.payload_json, TicketEvent.created_at)
            .where(TicketEvent.ticket_id == ticket_id)
            .order_by(TicketEvent.created_at.asc(), TicketEvent.id.asc())
        )
        result = await self.session.execute(statement)
        return tuple(
            TicketEventDetails(
                event_type=cast(TicketEventType, row[0]),
                payload_json=cast(dict[str, object] | None, row[1]),
                created_at=cast(datetime, row[2]),
            )
            for row in result.all()
        )
