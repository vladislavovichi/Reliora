from __future__ import annotations

from typing import cast

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.feedback import TicketFeedback as TicketFeedbackEntity
from infrastructure.db.models.feedback import TicketFeedback


class SqlAlchemyTicketFeedbackRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_ticket_id(self, *, ticket_id: int) -> TicketFeedbackEntity | None:
        result = await self.session.execute(
            select(TicketFeedback).where(TicketFeedback.ticket_id == ticket_id)
        )
        return cast(TicketFeedbackEntity | None, result.scalar_one_or_none())

    async def create(
        self,
        *,
        ticket_id: int,
        client_chat_id: int,
        rating: int,
    ) -> TicketFeedbackEntity:
        feedback = TicketFeedback(
            ticket_id=ticket_id,
            client_chat_id=client_chat_id,
            rating=rating,
        )
        self.session.add(feedback)
        try:
            await self.session.flush()
        except IntegrityError:
            await self.session.rollback()
            existing_feedback = await self.get_by_ticket_id(ticket_id=ticket_id)
            if existing_feedback is None:
                raise
            return existing_feedback
        return cast(TicketFeedbackEntity, feedback)

    async def update_comment(
        self,
        *,
        ticket_id: int,
        comment: str,
    ) -> TicketFeedbackEntity | None:
        feedback = await self.get_by_ticket_id(ticket_id=ticket_id)
        if feedback is None:
            return None

        feedback.comment = comment
        await self.session.flush()
        return feedback
