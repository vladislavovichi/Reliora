from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from uuid import UUID

from application.use_cases.tickets.common import (
    build_status_payload,
    build_ticket_summary,
    utcnow,
)
from application.use_cases.tickets.identifiers import format_public_ticket_number
from application.use_cases.tickets.summaries import (
    SLAAutoReassignmentTarget,
    SLABatchProcessingResult,
    SLADeadlineStatus,
    SLADeadlineSummary,
    TicketSLAEvaluationSummary,
    TicketSLAProcessingSummary,
    TicketSummary,
)
from domain.contracts.repositories import (
    OperatorRepository,
    SLAPolicyRecord,
    SLAPolicyRepository,
    TicketEventRepository,
    TicketRepository,
)
from domain.entities.ticket import Ticket
from domain.enums.tickets import TicketEventType, TicketStatus


def build_sla_approaching_window(*, total_minutes: int) -> timedelta:
    approaching_minutes = max(5, min(30, (total_minutes + 4) // 5))
    return timedelta(minutes=approaching_minutes)


def build_stale_assignment_window(policy: SLAPolicyRecord) -> timedelta:
    stale_minutes = min(
        policy.resolution_minutes,
        max(
            policy.first_response_minutes,
            max(15, policy.resolution_minutes // 4),
        ),
    )
    return timedelta(minutes=stale_minutes)


def evaluate_deadline(
    *,
    deadline_at: datetime | None,
    now: datetime,
    approaching_window: timedelta | None = None,
) -> SLADeadlineSummary:
    if deadline_at is None:
        return SLADeadlineSummary(
            deadline_at=None,
            status=SLADeadlineStatus.NOT_APPLICABLE,
            remaining_seconds=None,
        )

    remaining_seconds = int((deadline_at - now).total_seconds())
    if remaining_seconds <= 0:
        return SLADeadlineSummary(
            deadline_at=deadline_at,
            status=SLADeadlineStatus.BREACHED,
            remaining_seconds=remaining_seconds,
        )

    if (
        approaching_window is not None
        and remaining_seconds <= int(approaching_window.total_seconds())
    ):
        status = SLADeadlineStatus.APPROACHING
    else:
        status = SLADeadlineStatus.OK

    return SLADeadlineSummary(
        deadline_at=deadline_at,
        status=status,
        remaining_seconds=remaining_seconds,
    )


def build_sla_event_payload(
    *,
    policy: SLAPolicyRecord,
    deadline_at: datetime | None,
    checked_at: datetime,
    remaining_seconds: int | None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "policy_name": policy.name,
        "checked_at": checked_at.isoformat(),
    }
    if deadline_at is not None:
        payload["deadline_at"] = deadline_at.isoformat()
    if remaining_seconds is not None:
        payload["remaining_seconds"] = remaining_seconds
    return payload


def evaluate_ticket_sla(
    *,
    ticket: Ticket,
    policy: SLAPolicyRecord | None,
    now: datetime,
) -> TicketSLAEvaluationSummary:
    if policy is None:
        not_applicable = SLADeadlineSummary(
            deadline_at=None,
            status=SLADeadlineStatus.NOT_APPLICABLE,
            remaining_seconds=None,
        )
        return TicketSLAEvaluationSummary(
            public_id=ticket.public_id,
            public_number=format_public_ticket_number(ticket.public_id),
            status=ticket.status,
            assigned_operator_id=ticket.assigned_operator_id,
            policy_name=None,
            first_response=not_applicable,
            resolution=not_applicable,
            stale_assignment=not_applicable,
            should_auto_escalate=False,
            should_auto_reassign=False,
        )

    first_response_deadline_at: datetime | None = None
    if ticket.closed_at is None and ticket.first_response_at is None:
        first_response_deadline_at = ticket.created_at + timedelta(
            minutes=policy.first_response_minutes
        )

    resolution_deadline_at: datetime | None = None
    if ticket.closed_at is None:
        resolution_deadline_at = ticket.created_at + timedelta(
            minutes=policy.resolution_minutes
        )

    stale_assignment_deadline_at: datetime | None = None
    if (
        ticket.status == TicketStatus.ASSIGNED
        and ticket.assigned_operator_id is not None
        and ticket.closed_at is None
    ):
        stale_assignment_deadline_at = ticket.updated_at + build_stale_assignment_window(policy)

    first_response = evaluate_deadline(
        deadline_at=first_response_deadline_at,
        now=now,
        approaching_window=build_sla_approaching_window(
            total_minutes=policy.first_response_minutes
        ),
    )
    resolution = evaluate_deadline(
        deadline_at=resolution_deadline_at,
        now=now,
        approaching_window=build_sla_approaching_window(total_minutes=policy.resolution_minutes),
    )
    stale_assignment = evaluate_deadline(
        deadline_at=stale_assignment_deadline_at,
        now=now,
    )

    should_auto_escalate = (
        ticket.status in {TicketStatus.QUEUED, TicketStatus.ASSIGNED}
        and (
            first_response.status == SLADeadlineStatus.BREACHED
            or resolution.status == SLADeadlineStatus.BREACHED
        )
    )
    should_auto_reassign = (
        ticket.status == TicketStatus.ASSIGNED
        and ticket.assigned_operator_id is not None
        and stale_assignment.status == SLADeadlineStatus.BREACHED
        and not should_auto_escalate
    )

    return TicketSLAEvaluationSummary(
        public_id=ticket.public_id,
        public_number=format_public_ticket_number(ticket.public_id),
        status=ticket.status,
        assigned_operator_id=ticket.assigned_operator_id,
        policy_name=policy.name,
        first_response=first_response,
        resolution=resolution,
        stale_assignment=stale_assignment,
        should_auto_escalate=should_auto_escalate,
        should_auto_reassign=should_auto_reassign,
    )


class EvaluateTicketSLAStateUseCase:
    def __init__(
        self,
        ticket_repository: TicketRepository,
        sla_policy_repository: SLAPolicyRepository,
    ) -> None:
        self.ticket_repository = ticket_repository
        self.sla_policy_repository = sla_policy_repository

    async def __call__(
        self,
        *,
        ticket_public_id: UUID,
        now: datetime | None = None,
    ) -> TicketSLAEvaluationSummary | None:
        ticket = await self.ticket_repository.get_by_public_id(ticket_public_id)
        if ticket is None:
            return None

        checked_at = now or utcnow()
        policy = await self.sla_policy_repository.get_for_priority(priority=ticket.priority)
        return evaluate_ticket_sla(ticket=ticket, policy=policy, now=checked_at)


class AutoEscalateTicketBySLAUseCase:
    def __init__(
        self,
        ticket_repository: TicketRepository,
        ticket_event_repository: TicketEventRepository,
        sla_policy_repository: SLAPolicyRepository,
    ) -> None:
        self.ticket_repository = ticket_repository
        self.ticket_event_repository = ticket_event_repository
        self.sla_policy_repository = sla_policy_repository

    async def __call__(
        self,
        *,
        ticket_public_id: UUID,
        now: datetime | None = None,
    ) -> TicketSummary | None:
        ticket = await self.ticket_repository.get_by_public_id(ticket_public_id)
        if ticket is None or ticket.id is None:
            return None

        checked_at = now or utcnow()
        policy = await self.sla_policy_repository.get_for_priority(priority=ticket.priority)
        evaluation = evaluate_ticket_sla(ticket=ticket, policy=policy, now=checked_at)
        if not evaluation.should_auto_escalate:
            return None

        if (
            policy is not None
            and evaluation.first_response.status == SLADeadlineStatus.BREACHED
            and not await self.ticket_event_repository.exists(
                ticket_id=ticket.id,
                event_type=TicketEventType.SLA_BREACHED_FIRST_RESPONSE,
            )
        ):
            await self.ticket_event_repository.add(
                ticket_id=ticket.id,
                event_type=TicketEventType.SLA_BREACHED_FIRST_RESPONSE,
                payload_json=build_sla_event_payload(
                    policy=policy,
                    deadline_at=evaluation.first_response.deadline_at,
                    checked_at=checked_at,
                    remaining_seconds=evaluation.first_response.remaining_seconds,
                ),
            )

        if (
            policy is not None
            and evaluation.resolution.status == SLADeadlineStatus.BREACHED
            and not await self.ticket_event_repository.exists(
                ticket_id=ticket.id,
                event_type=TicketEventType.SLA_BREACHED_RESOLUTION,
            )
        ):
            await self.ticket_event_repository.add(
                ticket_id=ticket.id,
                event_type=TicketEventType.SLA_BREACHED_RESOLUTION,
                payload_json=build_sla_event_payload(
                    policy=policy,
                    deadline_at=evaluation.resolution.deadline_at,
                    checked_at=checked_at,
                    remaining_seconds=evaluation.resolution.remaining_seconds,
                ),
            )

        previous_status = ticket.status
        escalated_ticket = await self.ticket_repository.escalate(ticket_public_id=ticket_public_id)
        if escalated_ticket is None:
            return None

        reasons: list[str] = []
        if evaluation.first_response.status == SLADeadlineStatus.BREACHED:
            reasons.append(TicketEventType.SLA_BREACHED_FIRST_RESPONSE.value)
        if evaluation.resolution.status == SLADeadlineStatus.BREACHED:
            reasons.append(TicketEventType.SLA_BREACHED_RESOLUTION.value)

        await self.ticket_event_repository.add(
            ticket_id=ticket.id,
            event_type=TicketEventType.AUTO_ESCALATED,
            payload_json={
                **build_status_payload(
                    from_status=previous_status,
                    to_status=escalated_ticket.status,
                    assigned_operator_id=escalated_ticket.assigned_operator_id,
                ),
                "reasons": reasons,
                "checked_at": checked_at.isoformat(),
            },
        )

        return build_ticket_summary(escalated_ticket, event_type=TicketEventType.AUTO_ESCALATED)


class AutoReassignTicketBySLAUseCase:
    def __init__(
        self,
        ticket_repository: TicketRepository,
        ticket_event_repository: TicketEventRepository,
        operator_repository: OperatorRepository,
        sla_policy_repository: SLAPolicyRepository,
    ) -> None:
        self.ticket_repository = ticket_repository
        self.ticket_event_repository = ticket_event_repository
        self.operator_repository = operator_repository
        self.sla_policy_repository = sla_policy_repository

    async def __call__(
        self,
        *,
        ticket_public_id: UUID,
        telegram_user_id: int,
        display_name: str,
        username: str | None = None,
        now: datetime | None = None,
    ) -> TicketSummary | None:
        ticket = await self.ticket_repository.get_by_public_id(ticket_public_id)
        if ticket is None or ticket.id is None:
            return None

        checked_at = now or utcnow()
        policy = await self.sla_policy_repository.get_for_priority(priority=ticket.priority)
        evaluation = evaluate_ticket_sla(ticket=ticket, policy=policy, now=checked_at)
        if not evaluation.should_auto_reassign:
            return None

        operator_id = await self.operator_repository.get_or_create(
            telegram_user_id=telegram_user_id,
            display_name=display_name,
            username=username,
        )
        previous_status = ticket.status
        previous_operator_id = ticket.assigned_operator_id
        if previous_operator_id == operator_id:
            return None

        reassigned_ticket = await self.ticket_repository.assign_to_operator(
            ticket_public_id=ticket_public_id,
            operator_id=operator_id,
        )
        if reassigned_ticket is None:
            return None

        await self.ticket_event_repository.add(
            ticket_id=ticket.id,
            event_type=TicketEventType.AUTO_REASSIGNED,
            payload_json={
                **build_status_payload(
                    from_status=previous_status,
                    to_status=reassigned_ticket.status,
                    assigned_operator_id=operator_id,
                    previous_operator_id=previous_operator_id,
                ),
                "checked_at": checked_at.isoformat(),
                "reason": "stale_assigned_ticket",
            },
        )

        return build_ticket_summary(reassigned_ticket, event_type=TicketEventType.AUTO_REASSIGNED)


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
        self._evaluate_ticket_sla_state = EvaluateTicketSLAStateUseCase(
            ticket_repository=ticket_repository,
            sla_policy_repository=sla_policy_repository,
        )
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
        target_by_public_id = {
            target.ticket_public_id: target for target in reassignment_targets
        }

        processed: list[TicketSLAProcessingSummary] = []
        auto_escalated_count = 0
        auto_reassigned_count = 0

        for ticket in tickets:
            evaluation = await self._evaluate_ticket_sla_state(
                ticket_public_id=ticket.public_id,
                now=checked_at,
            )
            if evaluation is None:
                continue

            persisted_event_types: list[TicketEventType] = []
            if (
                ticket.id is not None
                and evaluation.policy_name is not None
                and evaluation.first_response.status == SLADeadlineStatus.BREACHED
                and not await self.ticket_event_repository.exists(
                    ticket_id=ticket.id,
                    event_type=TicketEventType.SLA_BREACHED_FIRST_RESPONSE,
                )
            ):
                policy = await self.sla_policy_repository.get_for_priority(priority=ticket.priority)
                if policy is not None:
                    await self.ticket_event_repository.add(
                        ticket_id=ticket.id,
                        event_type=TicketEventType.SLA_BREACHED_FIRST_RESPONSE,
                        payload_json=build_sla_event_payload(
                            policy=policy,
                            deadline_at=evaluation.first_response.deadline_at,
                            checked_at=checked_at,
                            remaining_seconds=evaluation.first_response.remaining_seconds,
                        ),
                    )
                    persisted_event_types.append(TicketEventType.SLA_BREACHED_FIRST_RESPONSE)

            if (
                ticket.id is not None
                and evaluation.policy_name is not None
                and evaluation.resolution.status == SLADeadlineStatus.BREACHED
                and not await self.ticket_event_repository.exists(
                    ticket_id=ticket.id,
                    event_type=TicketEventType.SLA_BREACHED_RESOLUTION,
                )
            ):
                policy = await self.sla_policy_repository.get_for_priority(priority=ticket.priority)
                if policy is not None:
                    await self.ticket_event_repository.add(
                        ticket_id=ticket.id,
                        event_type=TicketEventType.SLA_BREACHED_RESOLUTION,
                        payload_json=build_sla_event_payload(
                            policy=policy,
                            deadline_at=evaluation.resolution.deadline_at,
                            checked_at=checked_at,
                            remaining_seconds=evaluation.resolution.remaining_seconds,
                        ),
                    )
                    persisted_event_types.append(TicketEventType.SLA_BREACHED_RESOLUTION)

            escalated = await self._auto_escalate_ticket(
                ticket_public_id=ticket.public_id,
                now=checked_at,
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
