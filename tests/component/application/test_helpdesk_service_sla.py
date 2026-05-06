from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from application.use_cases.tickets.summaries import SLAAutoReassignmentTarget
from domain.enums.tickets import TicketEventType, TicketStatus

from .test_helpdesk_service import (
    StubTicketRepository,
    build_event_repository_mock,
    build_operator_repository_mock,
    build_service,
    build_sla_policy_repository_mock,
    build_ticket,
)


async def test_evaluate_ticket_sla_state_detects_approaching_deadlines() -> None:
    public_id = uuid4()
    now = datetime.now(UTC)
    ticket = build_ticket(
        ticket_id=1,
        public_id=public_id,
        status=TicketStatus.QUEUED,
        created_at=now - timedelta(minutes=26),
        updated_at=now - timedelta(minutes=5),
    )
    service = build_service(
        ticket_repository=StubTicketRepository(created_ticket=ticket),
        sla_policy_repository=build_sla_policy_repository_mock(
            policies={
                None: SimpleNamespace(
                    id=1,
                    name="Default",
                    first_response_minutes=30,
                    resolution_minutes=240,
                    priority=None,
                )
            }
        ),
    )

    result = await service.evaluate_ticket_sla_state(
        ticket_public_id=public_id,
        now=now,
    )

    assert result is not None
    assert result.policy_name == "Default"
    assert result.first_response.status.value == "approaching"
    assert result.resolution.status.value == "ok"
    assert result.should_auto_escalate is False
    assert result.should_auto_reassign is False


async def test_auto_escalate_ticket_by_sla_persists_breach_and_auto_escalated_events() -> None:
    public_id = uuid4()
    now = datetime.now(UTC)
    ticket = build_ticket(
        ticket_id=1,
        public_id=public_id,
        status=TicketStatus.ASSIGNED,
        assigned_operator_id=7,
        created_at=now - timedelta(minutes=90),
        updated_at=now - timedelta(minutes=45),
    )
    event_repository = build_event_repository_mock()
    service = build_service(
        ticket_repository=StubTicketRepository(created_ticket=ticket),
        event_repository=event_repository,
        sla_policy_repository=build_sla_policy_repository_mock(
            policies={
                None: SimpleNamespace(
                    id=1,
                    name="Default",
                    first_response_minutes=30,
                    resolution_minutes=240,
                    priority=None,
                )
            }
        ),
    )

    result = await service.auto_escalate_ticket_by_sla(
        ticket_public_id=public_id,
        now=now,
    )

    assert result is not None
    assert result.status == TicketStatus.ESCALATED
    assert result.event_type == TicketEventType.AUTO_ESCALATED
    assert [event["event_type"] for event in event_repository.added_events] == [
        TicketEventType.SLA_BREACHED_FIRST_RESPONSE,
        TicketEventType.AUTO_ESCALATED,
    ]


async def test_auto_reassign_ticket_by_sla_requires_stale_assignment() -> None:
    public_id = uuid4()
    now = datetime.now(UTC)
    ticket = build_ticket(
        ticket_id=1,
        public_id=public_id,
        status=TicketStatus.ASSIGNED,
        assigned_operator_id=7,
        created_at=now - timedelta(minutes=35),
        updated_at=now - timedelta(minutes=31),
        first_response_at=now - timedelta(minutes=34),
    )
    event_repository = build_event_repository_mock()
    service = build_service(
        ticket_repository=StubTicketRepository(created_ticket=ticket),
        event_repository=event_repository,
        operator_repository=build_operator_repository_mock({1002: 9}),
        sla_policy_repository=build_sla_policy_repository_mock(
            policies={
                None: SimpleNamespace(
                    id=1,
                    name="Default",
                    first_response_minutes=30,
                    resolution_minutes=120,
                    priority=None,
                )
            }
        ),
    )

    result = await service.auto_reassign_ticket_by_sla(
        ticket_public_id=public_id,
        telegram_user_id=1002,
        display_name="Operator Two",
        now=now,
    )

    assert result is not None
    assert result.status == TicketStatus.ASSIGNED
    assert result.event_type == TicketEventType.AUTO_REASSIGNED
    assert ticket.assigned_operator_id == 9
    assert [event["event_type"] for event in event_repository.added_events] == [
        TicketEventType.AUTO_REASSIGNED,
    ]


async def test_run_ticket_sla_checks_processes_escalation_and_reassignment_paths() -> None:
    now = datetime.now(UTC)
    escalated_ticket = build_ticket(
        ticket_id=1,
        public_id=uuid4(),
        status=TicketStatus.QUEUED,
        created_at=now - timedelta(minutes=45),
        updated_at=now - timedelta(minutes=45),
    )
    stale_ticket = build_ticket(
        ticket_id=2,
        public_id=uuid4(),
        status=TicketStatus.ASSIGNED,
        assigned_operator_id=7,
        created_at=now - timedelta(minutes=50),
        updated_at=now - timedelta(minutes=31),
        first_response_at=now - timedelta(minutes=49),
    )
    ticket_repository = StubTicketRepository(
        created_ticket=escalated_ticket,
        queued_tickets=[stale_ticket],
    )
    event_repository = build_event_repository_mock()
    service = build_service(
        ticket_repository=ticket_repository,
        event_repository=event_repository,
        operator_repository=build_operator_repository_mock({2001: 11}),
        sla_policy_repository=build_sla_policy_repository_mock(
            policies={
                None: SimpleNamespace(
                    id=1,
                    name="Default",
                    first_response_minutes=30,
                    resolution_minutes=120,
                    priority=None,
                )
            }
        ),
    )

    result = await service.run_ticket_sla_checks(
        now=now,
        reassignment_targets=(
            SLAAutoReassignmentTarget(
                ticket_public_id=stale_ticket.public_id,
                telegram_user_id=2001,
                display_name="Operator Eleven",
                username="operator11",
            ),
        ),
    )

    assert result.evaluated_count == 2
    assert result.auto_escalated_count == 1
    assert result.auto_reassigned_count == 1
    assert escalated_ticket.status == TicketStatus.ESCALATED
    assert stale_ticket.assigned_operator_id == 11
    assert [event["event_type"] for event in event_repository.added_events] == [
        TicketEventType.SLA_BREACHED_FIRST_RESPONSE,
        TicketEventType.AUTO_ESCALATED,
        TicketEventType.AUTO_REASSIGNED,
    ]
