from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime
from uuid import UUID

from application.contracts.runtime import SLADeadlineScheduler
from application.services.helpdesk.components import HelpdeskComponents
from application.use_cases.tickets.summaries import (
    SLAAutoReassignmentTarget,
    SLABatchProcessingResult,
    TicketSLAEvaluationSummary,
    TicketSummary,
)


class HelpdeskSLAOperations:
    _components: HelpdeskComponents
    sla_deadline_scheduler: SLADeadlineScheduler | None
    _ensure_permission: Callable[..., Awaitable[None]]

    async def _sync_sla_deadline(
        self,
        *,
        ticket_public_id: UUID,
    ) -> None:
        if self.sla_deadline_scheduler is None:
            return

        evaluation = await self._components.sla.evaluate_ticket_state(
            ticket_public_id=ticket_public_id,
        )
        if evaluation is None:
            return

        next_deadline_at = min(
            (
                deadline.deadline_at
                for deadline in (
                    evaluation.first_response,
                    evaluation.resolution,
                    evaluation.stale_assignment,
                )
                if deadline.deadline_at is not None
                and deadline.remaining_seconds is not None
                and deadline.remaining_seconds > 0
            ),
            default=None,
        )
        if next_deadline_at is None:
            await self.sla_deadline_scheduler.cancel(ticket_id=str(ticket_public_id))
            return

        await self.sla_deadline_scheduler.schedule(
            ticket_id=str(ticket_public_id),
            deadline_at=next_deadline_at,
        )

    async def evaluate_ticket_sla_state(
        self,
        *,
        ticket_public_id: UUID,
        now: datetime | None = None,
    ) -> TicketSLAEvaluationSummary | None:
        return await self._components.sla.evaluate_ticket_state(
            ticket_public_id=ticket_public_id,
            now=now,
        )

    async def auto_escalate_ticket_by_sla(
        self,
        *,
        ticket_public_id: UUID,
        now: datetime | None = None,
    ) -> TicketSummary | None:
        result = await self._components.sla.auto_escalate_ticket(
            ticket_public_id=ticket_public_id,
            now=now,
        )
        if result is not None:
            await self._sync_sla_deadline(ticket_public_id=result.public_id)
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
        result = await self._components.sla.auto_reassign_ticket(
            ticket_public_id=ticket_public_id,
            telegram_user_id=telegram_user_id,
            display_name=display_name,
            username=username,
            now=now,
        )
        if result is not None:
            await self._sync_sla_deadline(ticket_public_id=result.public_id)
        return result

    async def run_ticket_sla_checks(
        self,
        *,
        now: datetime | None = None,
        limit: int | None = None,
        reassignment_targets: Sequence[SLAAutoReassignmentTarget] = (),
    ) -> SLABatchProcessingResult:
        result = await self._components.sla.run_checks(
            now=now,
            limit=limit,
            reassignment_targets=reassignment_targets,
        )
        for item in result.processed_tickets:
            await self._sync_sla_deadline(ticket_public_id=item.evaluation.public_id)
        return result
