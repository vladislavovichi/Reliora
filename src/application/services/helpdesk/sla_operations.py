from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from application.services.helpdesk._context import _HelpdeskContext
from application.use_cases.tickets.summaries import (
    SLAAutoReassignmentTarget,
    SLABatchProcessingResult,
    TicketSLAEvaluationSummary,
    TicketSummary,
)


class HelpdeskSLAOperations:
    def __init__(self, ctx: _HelpdeskContext) -> None:
        self._ctx = ctx

    async def evaluate_ticket_sla_state(
        self,
        *,
        ticket_public_id: UUID,
        now: datetime | None = None,
    ) -> TicketSLAEvaluationSummary | None:
        return await self._ctx.components.sla.evaluate_ticket_state(
            ticket_public_id=ticket_public_id,
            now=now,
        )

    async def auto_escalate_ticket_by_sla(
        self,
        *,
        ticket_public_id: UUID,
        now: datetime | None = None,
    ) -> TicketSummary | None:
        result = await self._ctx.components.sla.auto_escalate_ticket(
            ticket_public_id=ticket_public_id,
            now=now,
        )
        if result is not None:
            await self._ctx.sync_sla_deadline(ticket_public_id=result.public_id)
        return result

    async def auto_reassign_ticket_by_sla(
        self,
        *,
        ticket_public_id: UUID,
        telegram_user_id: int,
        display_name: str,
        username: str | None = None,
        now: datetime | None = None,
    ) -> TicketSummary | None:
        result = await self._ctx.components.sla.auto_reassign_ticket(
            ticket_public_id=ticket_public_id,
            telegram_user_id=telegram_user_id,
            display_name=display_name,
            username=username,
            now=now,
        )
        if result is not None:
            await self._ctx.sync_sla_deadline(ticket_public_id=result.public_id)
        return result

    async def run_ticket_sla_checks(
        self,
        *,
        now: datetime | None = None,
        limit: int | None = None,
        reassignment_targets: Sequence[SLAAutoReassignmentTarget] = (),
    ) -> SLABatchProcessingResult:
        result = await self._ctx.components.sla.run_checks(
            now=now,
            limit=limit,
            reassignment_targets=reassignment_targets,
        )
        for item in result.processed_tickets:
            await self._ctx.sync_sla_deadline(ticket_public_id=item.evaluation.public_id)
        return result
