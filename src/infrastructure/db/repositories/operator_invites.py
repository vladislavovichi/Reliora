from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.db.models.operator_invite import OperatorInviteCode


class SqlAlchemyOperatorInviteCodeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        code_hash: str,
        created_by_telegram_user_id: int,
        expires_at: datetime,
        max_uses: int = 1,
    ) -> OperatorInviteCode:
        invite = OperatorInviteCode(
            code_hash=code_hash,
            created_by_telegram_user_id=created_by_telegram_user_id,
            expires_at=expires_at,
            max_uses=max_uses,
            used_count=0,
            is_active=True,
        )
        self.session.add(invite)
        await self.session.flush()
        return invite

    async def get_by_code_hash(self, *, code_hash: str) -> OperatorInviteCode | None:
        result = await self.session.execute(
            select(OperatorInviteCode).where(OperatorInviteCode.code_hash == code_hash).limit(1)
        )
        return result.scalar_one_or_none()

    async def mark_used(
        self,
        *,
        invite_id: int,
        telegram_user_id: int,
        used_at: datetime,
    ) -> OperatorInviteCode | None:
        result = await self.session.execute(
            select(OperatorInviteCode).where(OperatorInviteCode.id == invite_id).limit(1)
        )
        invite = result.scalar_one_or_none()
        if invite is None:
            return None

        invite.used_count += 1
        invite.last_used_at = used_at
        invite.last_used_telegram_user_id = telegram_user_id
        if invite.used_count >= invite.max_uses:
            invite.is_active = False
            invite.deactivated_at = used_at
        await self.session.flush()
        return invite
