from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from domain.contracts.repositories import (
    MacroRepository,
    OperatorRepository,
    SLAPolicyRepository,
    TagRepository,
    TicketEventRepository,
    TicketMessageRepository,
    TicketRepository,
    TicketTagRepository,
)
from domain.entities.ticket import Ticket as TicketEntity
from domain.entities.ticket import TicketDetails
from domain.enums.tickets import (
    TicketEventType,
    TicketMessageSenderType,
    TicketPriority,
    TicketStatus,
)
from infrastructure.db.models import (
    Macro,
    Operator,
    SLAPolicy,
    Tag,
    TicketEvent,
    TicketMessage,
    TicketTag,
)
from infrastructure.db.models import Ticket as TicketModel


def utcnow() -> datetime:
    return datetime.now(UTC)


def normalize_tag_name(name: str) -> str:
    return " ".join(name.strip().lower().split())


def apply_queue_ordering(
    statement: Select[tuple[TicketModel]],
    *,
    prioritize_priority: bool,
) -> Select[tuple[TicketModel]]:
    if not prioritize_priority:
        return statement.order_by(TicketModel.created_at.asc(), TicketModel.id.asc())

    priority_rank = case(
        (TicketModel.priority == TicketPriority.URGENT, 0),
        (TicketModel.priority == TicketPriority.HIGH, 1),
        (TicketModel.priority == TicketPriority.NORMAL, 2),
        (TicketModel.priority == TicketPriority.LOW, 3),
        else_=4,
    )
    return statement.order_by(
        priority_rank.asc(),
        TicketModel.created_at.asc(),
        TicketModel.id.asc(),
    )


class SqlAlchemyTicketRepository(TicketRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        client_chat_id: int,
        subject: str,
        priority: TicketPriority = TicketPriority.NORMAL,
    ) -> TicketEntity:
        ticket = TicketModel(
            public_id=uuid4(),
            client_chat_id=client_chat_id,
            status=TicketStatus.NEW,
            subject=subject,
            priority=priority,
        )
        self.session.add(ticket)
        await self.session.flush()
        return cast(TicketEntity, ticket)

    async def get_by_public_id(self, public_id: UUID) -> TicketEntity | None:
        statement = select(TicketModel).where(TicketModel.public_id == public_id)
        result = await self.session.execute(statement)
        ticket = result.scalar_one_or_none()
        return cast(TicketEntity | None, ticket)

    async def get_details_by_public_id(self, public_id: UUID) -> TicketDetails | None:
        ticket = await self.get_by_public_id(public_id)
        if ticket is None or ticket.id is None:
            return None

        assigned_operator_name: str | None = None
        if ticket.assigned_operator_id is not None:
            operator_statement = select(Operator.display_name).where(
                Operator.id == ticket.assigned_operator_id
            )
            operator_result = await self.session.execute(operator_statement)
            assigned_operator_name = operator_result.scalar_one_or_none()

        last_message_statement = (
            select(TicketMessage.text, TicketMessage.sender_type)
            .where(TicketMessage.ticket_id == ticket.id)
            .order_by(desc(TicketMessage.created_at), desc(TicketMessage.id))
            .limit(1)
        )
        last_message_result = await self.session.execute(last_message_statement)
        last_message_row = last_message_result.first()
        last_message_text: str | None = None
        last_message_sender_type: TicketMessageSenderType | None = None
        if last_message_row is not None:
            last_message_text = cast(str, last_message_row[0])
            last_message_sender_type = cast(
                TicketMessageSenderType, last_message_row[1]
            )

        tags_statement = (
            select(Tag.name)
            .join(TicketTag, TicketTag.tag_id == Tag.id)
            .where(TicketTag.ticket_id == ticket.id)
            .order_by(Tag.name.asc(), Tag.id.asc())
        )
        tags_result = await self.session.execute(tags_statement)
        tags = tuple(tags_result.scalars().all())

        return TicketDetails(
            id=ticket.id,
            public_id=ticket.public_id,
            client_chat_id=ticket.client_chat_id,
            status=ticket.status,
            priority=ticket.priority,
            subject=ticket.subject,
            assigned_operator_id=ticket.assigned_operator_id,
            assigned_operator_name=assigned_operator_name,
            created_at=ticket.created_at,
            updated_at=ticket.updated_at,
            first_response_at=ticket.first_response_at,
            closed_at=ticket.closed_at,
            tags=tags,
            last_message_text=last_message_text,
            last_message_sender_type=last_message_sender_type,
        )

    async def get_active_by_client_chat_id(
        self, client_chat_id: int
    ) -> TicketEntity | None:
        statement = (
            select(TicketModel)
            .where(TicketModel.client_chat_id == client_chat_id)
            .where(TicketModel.status != TicketStatus.CLOSED)
            .order_by(desc(TicketModel.updated_at), desc(TicketModel.created_at))
            .limit(1)
        )
        result = await self.session.execute(statement)
        ticket = result.scalar_one_or_none()
        return cast(TicketEntity | None, ticket)

    async def get_next_queued_ticket(
        self, *, prioritize_priority: bool = False
    ) -> TicketEntity | None:
        statement = apply_queue_ordering(
            select(TicketModel)
            .where(TicketModel.status == TicketStatus.QUEUED)
            .limit(1),
            prioritize_priority=prioritize_priority,
        )
        result = await self.session.execute(statement)
        ticket = result.scalar_one_or_none()
        return cast(TicketEntity | None, ticket)

    async def list_queued_tickets(
        self,
        *,
        limit: int | None = None,
        prioritize_priority: bool = False,
    ) -> Sequence[TicketEntity]:
        statement = apply_queue_ordering(
            select(TicketModel).where(TicketModel.status == TicketStatus.QUEUED),
            prioritize_priority=prioritize_priority,
        )
        if limit is not None:
            statement = statement.limit(limit)

        result = await self.session.execute(statement)
        tickets = result.scalars().all()
        return cast(Sequence[TicketEntity], tickets)

    async def list_open_tickets(self, *, limit: int | None = None) -> Sequence[TicketEntity]:
        statement = (
            select(TicketModel)
            .where(TicketModel.status != TicketStatus.CLOSED)
            .order_by(TicketModel.updated_at.asc(), TicketModel.id.asc())
        )
        if limit is not None:
            statement = statement.limit(limit)

        result = await self.session.execute(statement)
        tickets = result.scalars().all()
        return cast(Sequence[TicketEntity], tickets)

    async def enqueue(self, *, ticket_public_id: UUID) -> TicketEntity | None:
        ticket = await self.get_by_public_id(ticket_public_id)
        if ticket is None:
            return None

        ticket.status = TicketStatus.QUEUED
        await self.session.flush()
        return ticket

    async def assign_queued_to_operator(
        self, *, ticket_public_id: UUID, operator_id: int
    ) -> TicketEntity | None:
        ticket = await self.get_by_public_id(ticket_public_id)
        if ticket is None or ticket.status != TicketStatus.QUEUED:
            return None

        ticket.assigned_operator_id = operator_id
        ticket.status = TicketStatus.ASSIGNED
        await self.session.flush()
        return ticket

    async def assign_to_operator(
        self, *, ticket_public_id: UUID, operator_id: int
    ) -> TicketEntity | None:
        ticket = await self.get_by_public_id(ticket_public_id)
        if ticket is None:
            return None

        ticket.assigned_operator_id = operator_id
        ticket.status = TicketStatus.ASSIGNED
        await self.session.flush()
        return ticket

    async def escalate(self, *, ticket_public_id: UUID) -> TicketEntity | None:
        ticket = await self.get_by_public_id(ticket_public_id)
        if ticket is None:
            return None

        ticket.status = TicketStatus.ESCALATED
        await self.session.flush()
        return ticket

    async def close(self, *, ticket_public_id: UUID) -> TicketEntity | None:
        ticket = await self.get_by_public_id(ticket_public_id)
        if ticket is None:
            return None

        ticket.status = TicketStatus.CLOSED
        ticket.closed_at = utcnow()
        await self.session.flush()
        return ticket

    async def count_by_status(self) -> Mapping[TicketStatus, int]:
        statement = select(TicketModel.status, func.count(TicketModel.id)).group_by(
            TicketModel.status
        )
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


class SqlAlchemyTicketEventRepository(TicketEventRepository):
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
        statement = select(Operator).where(
            Operator.telegram_user_id == telegram_user_id
        )
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


class SqlAlchemyMacroRepository(MacroRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_all(self) -> Sequence[Macro]:
        statement = select(Macro).order_by(Macro.title.asc(), Macro.id.asc())
        result = await self.session.execute(statement)
        return result.scalars().all()

    async def get_by_id(self, *, macro_id: int) -> Macro | None:
        statement = select(Macro).where(Macro.id == macro_id)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()


class SqlAlchemySLAPolicyRepository(SLAPolicyRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_for_priority(
        self, *, priority: TicketPriority
    ) -> SLAPolicy | None:
        priority_rank = case(
            (SLAPolicy.priority == priority, 0),
            else_=1,
        )
        statement = (
            select(SLAPolicy)
            .where(
                (SLAPolicy.priority == priority) | (SLAPolicy.priority.is_(None))
            )
            .order_by(priority_rank.asc(), SLAPolicy.id.asc())
            .limit(1)
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()


class SqlAlchemyTagRepository(TagRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create(self, *, name: str) -> int:
        normalized_name = normalize_tag_name(name)
        statement = select(Tag).where(Tag.name == normalized_name)
        result = await self.session.execute(statement)
        tag = result.scalar_one_or_none()

        if tag is None:
            tag = Tag(name=normalized_name)
            self.session.add(tag)
            await self.session.flush()

        return tag.id

    async def get_by_name(self, *, name: str) -> Tag | None:
        normalized_name = normalize_tag_name(name)
        statement = select(Tag).where(Tag.name == normalized_name)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def list_all(self) -> Sequence[Tag]:
        statement = select(Tag).order_by(Tag.name.asc(), Tag.id.asc())
        result = await self.session.execute(statement)
        return result.scalars().all()


class SqlAlchemyTicketTagRepository(TicketTagRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_ticket(self, *, ticket_id: int) -> Sequence[Tag]:
        statement = (
            select(Tag)
            .join(TicketTag, TicketTag.tag_id == Tag.id)
            .where(TicketTag.ticket_id == ticket_id)
            .order_by(Tag.name.asc(), Tag.id.asc())
        )
        result = await self.session.execute(statement)
        return result.scalars().all()

    async def add(self, *, ticket_id: int, tag_id: int) -> bool:
        statement = select(TicketTag).where(
            TicketTag.ticket_id == ticket_id,
            TicketTag.tag_id == tag_id,
        )
        result = await self.session.execute(statement)
        ticket_tag = result.scalar_one_or_none()
        if ticket_tag is not None:
            return False

        self.session.add(TicketTag(ticket_id=ticket_id, tag_id=tag_id))
        await self.session.flush()
        return True

    async def remove(self, *, ticket_id: int, tag_id: int) -> bool:
        statement = select(TicketTag).where(
            TicketTag.ticket_id == ticket_id,
            TicketTag.tag_id == tag_id,
        )
        result = await self.session.execute(statement)
        ticket_tag = result.scalar_one_or_none()
        if ticket_tag is None:
            return False

        await self.session.delete(ticket_tag)
        await self.session.flush()
        return True
