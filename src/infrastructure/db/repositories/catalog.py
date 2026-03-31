from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.enums.tickets import TicketPriority
from infrastructure.db.models import Macro, SLAPolicy, Tag, TicketTag
from infrastructure.db.repositories.base import normalize_tag_name


class SqlAlchemyMacroRepository:
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


class SqlAlchemySLAPolicyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_for_priority(self, *, priority: TicketPriority) -> SLAPolicy | None:
        priority_rank = case(
            (SLAPolicy.priority == priority, 0),
            else_=1,
        )
        statement = (
            select(SLAPolicy)
            .where((SLAPolicy.priority == priority) | (SLAPolicy.priority.is_(None)))
            .order_by(priority_rank.asc(), SLAPolicy.id.asc())
            .limit(1)
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()


class SqlAlchemyTagRepository:
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


class SqlAlchemyTicketTagRepository:
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
