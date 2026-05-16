from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import datetime

from application.use_cases.tickets.common import utcnow
from application.use_cases.tickets.sla_automation import (
    AutoEscalateTicketBySLAUseCase,
    AutoReassignTicketBySLAUseCase,
)
from application.use_cases.tickets.sla_evaluation import (
    evaluate_ticket_sla,
    persist_sla_breach_events,
)
from application.use_cases.tickets.summaries import (
    SLAAutoReassignmentTarget,
    SLABatchProcessingResult,
    TicketSLAProcessingSummary,
)
from domain.contracts.repositories import (
    OperatorRepository,
    SLAPolicyRepository,
    TicketEventRepository,
    TicketRepository,
)
from domain.enums.tickets import TicketEventType


class RunTicketSLAChecksUseCase:
    def __init__(
        self,
        ticket_repository: TicketRepository,
        ticket_event_repository: TicketEventRepository,
        operator_repository: OperatorRepository,
        sla_policy_repository: SLAPolicyRepository,
    ) -> None:
        self.ticket_repository = ticket_repository
        self.ticket_event_repository = ticket_event_repository
        self.sla_policy_repository = sla_policy_repository
        self._auto_escalate_ticket = AutoEscalateTicketBySLAUseCase(
            ticket_repository=ticket_repository,
            ticket_event_repository=ticket_event_repository,
            sla_policy_repository=sla_policy_repository,
        )
        self._auto_reassign_ticket = AutoReassignTicketBySLAUseCase(
            ticket_repository=ticket_repository,
            ticket_event_repository=ticket_event_repository,
            operator_repository=operator_repository,
            sla_policy_repository=sla_policy_repository,
        )

    async def __call__(
        self,
        *,
        now: datetime | None = None,
        limit: int | None = None,
        reassignment_targets: Sequence[SLAAutoReassignmentTarget] = (),
    ) -> SLABatchProcessingResult:
        checked_at = now or utcnow()
        tickets = await self.ticket_repository.list_open_tickets(limit=limit)
        target_by_public_id = {target.ticket_public_id: target for target in reassignment_targets}
        priorities = list({ticket.priority for ticket in tickets})
        policies = await asyncio.gather(
            *[self.sla_policy_repository.get_for_priority(priority=p) for p in priorities]
        )
        policy_by_priority = dict(zip(priorities, policies))

        processed: list[TicketSLAProcessingSummary] = []
        auto_escalated_count = 0
        auto_reassigned_count = 0

        for ticket in tickets:
            policy = policy_by_priority[ticket.priority]
            evaluation = evaluate_ticket_sla(
                ticket=ticket,
                policy=policy,
                now=checked_at,
            )

            persisted_event_types = list(
                await persist_sla_breach_events(
                    ticket=ticket,
                    evaluation=evaluation,
                    policy=policy,
                    checked_at=checked_at,
                    ticket_event_repository=self.ticket_event_repository,
                )
            )

            escalated = await self._auto_escalate_ticket(
                ticket_public_id=ticket.public_id,
                now=checked_at,
                ticket=ticket,
                policy=policy,
                evaluation=evaluation,
                persist_breaches=False,
            )
            if escalated is not None:
                auto_escalated_count += 1
                persisted_event_types.append(TicketEventType.AUTO_ESCALATED)
                processed.append(
                    TicketSLAProcessingSummary(
                        evaluation=evaluation,
                        persisted_event_types=tuple(dict.fromkeys(persisted_event_types)),
                    )
                )
                continue

            reassignment_target = target_by_public_id.get(ticket.public_id)
            if reassignment_target is not None:
                reassigned = await self._auto_reassign_ticket(
                    ticket_public_id=ticket.public_id,
                    telegram_user_id=reassignment_target.telegram_user_id,
                    display_name=reassignment_target.display_name,
                    username=reassignment_target.username,
                    now=checked_at,
                    ticket=ticket,
                    policy=policy,
                    evaluation=evaluation,
                )
                if reassigned is not None:
                    auto_reassigned_count += 1
                    persisted_event_types.append(TicketEventType.AUTO_REASSIGNED)

            processed.append(
                TicketSLAProcessingSummary(
                    evaluation=evaluation,
                    persisted_event_types=tuple(dict.fromkeys(persisted_event_types)),
                )
            )

        return SLABatchProcessingResult(
            processed_tickets=tuple(processed),
            evaluated_count=len(processed),
            auto_escalated_count=auto_escalated_count,
            auto_reassigned_count=auto_reassigned_count,
        )
