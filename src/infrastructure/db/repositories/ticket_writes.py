from __future__ import annotations

from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.ticket import Ticket as TicketEntity
from domain.enums.tickets import TicketPriority, TicketStatus
from infrastructure.db.models.ticket import Ticket as TicketModel
from infrastructure.db.repositories.base import utcnow


class SqlAlchemyTicketWriteRepository:
    session: AsyncSession

    async def create(
        self,
        *,
        client_chat_id: int,
        subject: str,
        category_id: int | None = None,
        priority: TicketPriority = TicketPriority.NORMAL,
    ) -> TicketEntity:
        ticket = TicketModel(
            public_id=uuid4(),
            client_chat_id=client_chat_id,
            status=TicketStatus.NEW,
            subject=subject,
            category_id=category_id,
            priority=priority,
        )
        self.session.add(ticket)
        await self.session.flush()
        return cast(TicketEntity, ticket)

    async def enqueue(self, *, ticket_public_id: UUID) -> TicketEntity | None:
        ticket = cast(TicketEntity | None, await cast(Any, self).get_by_public_id(ticket_public_id))
        if ticket is None:
            return None

        ticket.status = TicketStatus.QUEUED
        await self.session.flush()
        return ticket

    async def assign_queued_to_operator(
        self,
        *,
        ticket_public_id: UUID,
        operator_id: int,
    ) -> TicketEntity | None:
        ticket = cast(TicketEntity | None, await cast(Any, self).get_by_public_id(ticket_public_id))
        if ticket is None or ticket.status != TicketStatus.QUEUED:
            return None

        ticket.assigned_operator_id = operator_id
        ticket.status = TicketStatus.ASSIGNED
        await self.session.flush()
        return ticket

    async def assign_to_operator(
        self,
        *,
        ticket_public_id: UUID,
        operator_id: int,
    ) -> TicketEntity | None:
        ticket = cast(TicketEntity | None, await cast(Any, self).get_by_public_id(ticket_public_id))
        if ticket is None:
            return None

        ticket.assigned_operator_id = operator_id
        ticket.status = TicketStatus.ASSIGNED
        await self.session.flush()
        return ticket

    async def escalate(self, *, ticket_public_id: UUID) -> TicketEntity | None:
        ticket = cast(TicketEntity | None, await cast(Any, self).get_by_public_id(ticket_public_id))
        if ticket is None:
            return None

        ticket.status = TicketStatus.ESCALATED
        await self.session.flush()
        return ticket

    async def close(self, *, ticket_public_id: UUID) -> TicketEntity | None:
        ticket = cast(TicketEntity | None, await cast(Any, self).get_by_public_id(ticket_public_id))
        if ticket is None:
            return None

        ticket.status = TicketStatus.CLOSED
        ticket.closed_at = utcnow()
        await self.session.flush()
        return ticket
