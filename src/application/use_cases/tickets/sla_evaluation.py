from datetime import datetime, timedelta
from uuid import UUID

from application.use_cases.tickets.common import utcnow
from application.use_cases.tickets.identifiers import format_public_ticket_number
from application.use_cases.tickets.summaries import (
    SLADeadlineStatus,
    SLADeadlineSummary,
    TicketSLAEvaluationSummary,
)
from domain.contracts.repositories import (
    SLAPolicyRecord,
    SLAPolicyRepository,
    TicketEventRepository,
    TicketRepository,
)
from domain.entities.ticket import Ticket
from domain.enums.tickets import TicketEventType, TicketStatus

MINIMUM_STALE_ASSIGNMENT_WINDOW_MINUTES = 15
STALE_ASSIGNMENT_RESOLUTION_FRACTION = 4


def build_sla_approaching_window(*, total_minutes: int) -> timedelta:
    approaching_minutes = max(5, min(30, (total_minutes + 4) // 5))
    return timedelta(minutes=approaching_minutes)


def build_stale_assignment_window(policy: SLAPolicyRecord) -> timedelta:
    minimum_window_minutes = MINIMUM_STALE_ASSIGNMENT_WINDOW_MINUTES
    resolution_based_window_minutes = (
        policy.resolution_minutes // STALE_ASSIGNMENT_RESOLUTION_FRACTION
    )
    first_response_floor_minutes = policy.first_response_minutes

    # The stale-assignment window never drops below the minimum, should be at
    # least as long as the first-response SLA, and cannot exceed resolution SLA.
    uncapped_stale_minutes = max(
        first_response_floor_minutes,
        minimum_window_minutes,
        resolution_based_window_minutes,
    )
    stale_minutes = min(policy.resolution_minutes, uncapped_stale_minutes)
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

    status = (
        SLADeadlineStatus.APPROACHING
        if approaching_window is not None
        and remaining_seconds <= int(approaching_window.total_seconds())
        else SLADeadlineStatus.OK
    )
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

    first_response_deadline_at = build_first_response_deadline(ticket=ticket, policy=policy)
    resolution_deadline_at = build_resolution_deadline(ticket=ticket, policy=policy)
    stale_assignment_deadline_at = build_stale_assignment_deadline(ticket=ticket, policy=policy)

    first_response = evaluate_deadline(
        deadline_at=first_response_deadline_at,
        now=now,
        approaching_window=build_sla_approaching_window(
            total_minutes=policy.first_response_minutes,
        ),
    )
    resolution = evaluate_deadline(
        deadline_at=resolution_deadline_at,
        now=now,
        approaching_window=build_sla_approaching_window(
            total_minutes=policy.resolution_minutes,
        ),
    )
    stale_assignment = evaluate_deadline(
        deadline_at=stale_assignment_deadline_at,
        now=now,
    )

    should_auto_escalate = ticket.status in {TicketStatus.QUEUED, TicketStatus.ASSIGNED} and (
        first_response.status == SLADeadlineStatus.BREACHED
        or resolution.status == SLADeadlineStatus.BREACHED
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


def build_first_response_deadline(
    *,
    ticket: Ticket,
    policy: SLAPolicyRecord,
) -> datetime | None:
    if ticket.closed_at is not None or ticket.first_response_at is not None:
        return None
    return ticket.created_at + timedelta(minutes=policy.first_response_minutes)


def build_resolution_deadline(
    *,
    ticket: Ticket,
    policy: SLAPolicyRecord,
) -> datetime | None:
    if ticket.closed_at is not None:
        return None
    return ticket.created_at + timedelta(minutes=policy.resolution_minutes)


def build_stale_assignment_deadline(
    *,
    ticket: Ticket,
    policy: SLAPolicyRecord,
) -> datetime | None:
    if (
        ticket.status != TicketStatus.ASSIGNED
        or ticket.assigned_operator_id is None
        or ticket.closed_at is not None
    ):
        return None
    return ticket.updated_at + build_stale_assignment_window(policy)


async def persist_sla_breach_events(
    *,
    ticket: Ticket,
    evaluation: TicketSLAEvaluationSummary,
    policy: SLAPolicyRecord | None,
    checked_at: datetime,
    ticket_event_repository: TicketEventRepository,
) -> tuple[TicketEventType, ...]:
    if ticket.id is None or policy is None:
        return ()

    persisted_event_types: list[TicketEventType] = []
    for event_type, deadline in (
        (TicketEventType.SLA_BREACHED_FIRST_RESPONSE, evaluation.first_response),
        (TicketEventType.SLA_BREACHED_RESOLUTION, evaluation.resolution),
    ):
        if deadline.status != SLADeadlineStatus.BREACHED:
            continue
        if await ticket_event_repository.exists(ticket_id=ticket.id, event_type=event_type):
            continue

        await ticket_event_repository.add(
            ticket_id=ticket.id,
            event_type=event_type,
            payload_json=build_sla_event_payload(
                policy=policy,
                deadline_at=deadline.deadline_at,
                checked_at=checked_at,
                remaining_seconds=deadline.remaining_seconds,
            ),
        )
        persisted_event_types.append(event_type)

    return tuple(persisted_event_types)


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
