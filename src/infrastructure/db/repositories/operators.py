from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.db.models import Operator


class SqlAlchemyOperatorRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def exists_active_by_telegram_user_id(self, *, telegram_user_id: int) -> bool:
        statement = (
            select(Operator.id)
            .where(
                Operator.telegram_user_id == telegram_user_id,
                Operator.is_active.is_(True),
            )
            .limit(1)
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none() is not None

    async def list_active(self) -> Sequence[Operator]:
        statement = (
            select(Operator)
            .where(Operator.is_active.is_(True))
            .order_by(Operator.display_name.asc(), Operator.id.asc())
        )
        result = await self.session.execute(statement)
        return result.scalars().all()

    async def promote(
        self,
        *,
        telegram_user_id: int,
        display_name: str,
        username: str | None = None,
    ) -> Operator:
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
            operator.display_name = display_name
            if username is not None:
                operator.username = username
            operator.is_active = True

        await self.session.flush()
        return operator

    async def revoke(self, *, telegram_user_id: int) -> Operator | None:
        statement = (
            select(Operator)
            .where(
                Operator.telegram_user_id == telegram_user_id,
                Operator.is_active.is_(True),
            )
            .limit(1)
        )
        result = await self.session.execute(statement)
        operator = result.scalar_one_or_none()
        if operator is None:
            return None

        operator.is_active = False
        await self.session.flush()
        return operator

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
