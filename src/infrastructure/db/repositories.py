from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.contracts.repositories import (
    OperatorRepository,
    TagRepository,
    TicketMessageRepository,
    TicketRepository,
)
from domain.enums.tickets import TicketMessageSenderType, TicketPriority, TicketStatus
from infrastructure.db.models import Operator, Tag, Ticket, TicketMessage


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SqlAlchemyTicketRepository(TicketRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        client_chat_id: int,
        subject: str,
        priority: TicketPriority = TicketPriority.NORMAL,
    ) -> Ticket:
        ticket = Ticket(
            public_id=uuid4(),
            client_chat_id=client_chat_id,
            status=TicketStatus.NEW,
            subject=subject,
            priority=priority,
        )
        self.session.add(ticket)
        await self.session.flush()
        return ticket

    async def get_by_public_id(self, public_id: UUID) -> Ticket | None:
        statement = select(Ticket).where(Ticket.public_id == public_id)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def assign_to_operator(self, *, ticket_public_id: UUID, operator_id: int) -> Ticket | None:
        ticket = await self.get_by_public_id(ticket_public_id)
        if ticket is None:
            return None

        ticket.assigned_operator_id = operator_id
        ticket.status = TicketStatus.ASSIGNED
        await self.session.flush()
        return ticket

    async def close(self, *, ticket_public_id: UUID) -> Ticket | None:
        ticket = await self.get_by_public_id(ticket_public_id)
        if ticket is None:
            return None

        ticket.status = TicketStatus.CLOSED
        ticket.closed_at = utcnow()
        await self.session.flush()
        return ticket

    async def count_by_status(self) -> Mapping[TicketStatus, int]:
        statement = select(Ticket.status, func.count(Ticket.id)).group_by(Ticket.status)
        result = await self.session.execute(statement)
        return {status: count for status, count in result.all()}


class SqlAlchemyTicketMessageRepository(TicketMessageRepository):
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


class SqlAlchemyOperatorRepository(OperatorRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create(
        self,
        *,
        telegram_user_id: int,
        display_name: str,
        username: str | None = None,
    ) -> int:
        statement = select(Operator).where(Operator.telegram_user_id == telegram_user_id)
        result = await self.session.execute(statement)
        operator = result.scalar_one_or_none()

        if operator is None:
            operator = Operator(
                telegram_user_id=telegram_user_id,
                username=username,
                display_name=display_name,
                is_active=True,
            )
            self.session.add(operator)
        else:
            operator.username = username
            operator.display_name = display_name
            operator.is_active = True

        await self.session.flush()
        return operator.id


class SqlAlchemyTagRepository(TagRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create(self, *, name: str) -> int:
        normalized_name = name.strip().lower()
        statement = select(Tag).where(Tag.name == normalized_name)
        result = await self.session.execute(statement)
        tag = result.scalar_one_or_none()

        if tag is None:
            tag = Tag(name=normalized_name)
            self.session.add(tag)
            await self.session.flush()

        return tag.id
