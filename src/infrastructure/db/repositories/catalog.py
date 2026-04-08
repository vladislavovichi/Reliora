from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.enums.tickets import TicketPriority
from infrastructure.db.models.catalog import Macro, SLAPolicy, Tag, TicketCategory
from infrastructure.db.models.ticket import TicketTag
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

    async def get_by_title(self, *, title: str) -> Macro | None:
        statement = select(Macro).where(Macro.title == title)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def create(self, *, title: str, body: str) -> Macro:
        macro = Macro(title=title, body=body)
        self.session.add(macro)
        await self.session.flush()
        return macro

    async def update_title(self, *, macro_id: int, title: str) -> Macro | None:
        macro = await self.get_by_id(macro_id=macro_id)
        if macro is None:
            return None
        macro.title = title
        await self.session.flush()
        return macro

    async def update_body(self, *, macro_id: int, body: str) -> Macro | None:
        macro = await self.get_by_id(macro_id=macro_id)
        if macro is None:
            return None
        macro.body = body
        await self.session.flush()
        return macro

    async def delete(self, *, macro_id: int) -> Macro | None:
        macro = await self.get_by_id(macro_id=macro_id)
        if macro is None:
            return None
        await self.session.delete(macro)
        await self.session.flush()
        return macro


class SqlAlchemyTicketCategoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_all(self, *, include_inactive: bool = True) -> Sequence[TicketCategory]:
        statement = select(TicketCategory)
        if not include_inactive:
            statement = statement.where(TicketCategory.is_active.is_(True))
        statement = statement.order_by(
            TicketCategory.sort_order.asc(),
            TicketCategory.title.asc(),
            TicketCategory.id.asc(),
        )
        result = await self.session.execute(statement)
        return result.scalars().all()

    async def get_by_id(self, *, category_id: int) -> TicketCategory | None:
        statement = select(TicketCategory).where(TicketCategory.id == category_id)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_code(self, *, code: str) -> TicketCategory | None:
        statement = select(TicketCategory).where(TicketCategory.code == code)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        code: str,
        title: str,
        sort_order: int,
        is_active: bool = True,
    ) -> TicketCategory:
        category = TicketCategory(
            code=code,
            title=title,
            sort_order=sort_order,
            is_active=is_active,
        )
        self.session.add(category)
        await self.session.flush()
        return category

    async def update_title(
        self,
        *,
        category_id: int,
        title: str,
    ) -> TicketCategory | None:
        category = await self.get_by_id(category_id=category_id)
        if category is None:
            return None
        category.title = title
        await self.session.flush()
        return category

    async def set_active(
        self,
        *,
        category_id: int,
        is_active: bool,
    ) -> TicketCategory | None:
        category = await self.get_by_id(category_id=category_id)
        if category is None:
            return None
        category.is_active = is_active
        await self.session.flush()
        return category

    async def get_next_sort_order(self) -> int:
        statement = select(func.max(TicketCategory.sort_order))
        result = await self.session.execute(statement)
        current_max = result.scalar_one_or_none()
        return (int(current_max) if current_max is not None else 0) + 10


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
