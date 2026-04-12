from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.ai import TicketAISummaryDetails
from infrastructure.db.models.ai import TicketAISummary


class SqlAlchemyTicketAISummaryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_ticket_id(self, *, ticket_id: int) -> TicketAISummaryDetails | None:
        result = await self.session.execute(
            select(TicketAISummary).where(TicketAISummary.ticket_id == ticket_id).limit(1)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return _build_summary_details(row)

    async def upsert(
        self,
        *,
        ticket_id: int,
        short_summary: str,
        user_goal: str,
        actions_taken: str,
        current_status: str,
        generated_at: datetime,
        source_ticket_updated_at: datetime,
        source_message_count: int,
        source_internal_note_count: int,
        model_id: str | None,
    ) -> TicketAISummaryDetails:
        result = await self.session.execute(
            select(TicketAISummary).where(TicketAISummary.ticket_id == ticket_id).limit(1)
        )
        record = result.scalar_one_or_none()
        if record is None:
            record = TicketAISummary(
                ticket_id=ticket_id,
                short_summary=short_summary,
                user_goal=user_goal,
                actions_taken=actions_taken,
                current_status=current_status,
                generated_at=generated_at,
                source_ticket_updated_at=source_ticket_updated_at,
                source_message_count=source_message_count,
                source_internal_note_count=source_internal_note_count,
                model_id=model_id,
            )
            self.session.add(record)
        else:
            record.short_summary = short_summary
            record.user_goal = user_goal
            record.actions_taken = actions_taken
            record.current_status = current_status
            record.generated_at = generated_at
            record.source_ticket_updated_at = source_ticket_updated_at
            record.source_message_count = source_message_count
            record.source_internal_note_count = source_internal_note_count
            record.model_id = model_id
        await self.session.flush()
        return _build_summary_details(record)


def _build_summary_details(record: TicketAISummary) -> TicketAISummaryDetails:
    return TicketAISummaryDetails(
        ticket_id=record.ticket_id,
        short_summary=record.short_summary,
        user_goal=record.user_goal,
        actions_taken=record.actions_taken,
        current_status=record.current_status,
        generated_at=record.generated_at,
        source_ticket_updated_at=record.source_ticket_updated_at,
        source_message_count=record.source_message_count,
        source_internal_note_count=record.source_internal_note_count,
        model_id=record.model_id,
    )
