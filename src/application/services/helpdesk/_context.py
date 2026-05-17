from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from application.contracts.runtime import SLADeadlineScheduler
from application.services.audit import AuditTrail
from application.services.authorization import Permission
from application.services.helpdesk.components import HelpdeskComponents


@dataclass(slots=True)
class _HelpdeskContext:
    components: HelpdeskComponents
    audit: AuditTrail
    sla_deadline_scheduler: SLADeadlineScheduler | None

    async def ensure_permission(
        self,
        *,
        permission: Permission,
        telegram_user_id: int | None,
    ) -> None:
        await self.components.permissions.ensure_allowed(
            permission=permission,
            telegram_user_id=telegram_user_id,
        )

    async def require_permission_if_actor(
        self,
        *,
        permission: Permission,
        actor_telegram_user_id: int | None,
    ) -> None:
        if actor_telegram_user_id is None:
            return
        await self.ensure_permission(
            permission=permission,
            telegram_user_id=actor_telegram_user_id,
        )

    async def sync_sla_deadline(self, *, ticket_public_id: UUID) -> None:
        if self.sla_deadline_scheduler is None:
            return

        evaluation = await self.components.sla.evaluate_ticket_state(
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
