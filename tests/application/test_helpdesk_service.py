from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from application.services.helpdesk import HelpdeskService
from domain.enums.tickets import TicketEventType, TicketMessageSenderType, TicketStatus
from domain.tickets import InvalidTicketTransitionError


@dataclass
class StubTicketRepository:
    created_ticket: SimpleNamespace
    active_ticket: SimpleNamespace | None = None
    by_status: dict[TicketStatus, int] | None = None

    def __post_init__(self) -> None:
        self.create_calls: list[dict[str, object]] = []
        self.active_lookup_calls: list[int] = []
        self.enqueue_calls: list[UUID] = []
        self.assign_calls: list[dict[str, object]] = []
        self.escalate_calls: list[UUID] = []
        self.close_calls: list[UUID] = []
        self.tickets: dict[UUID, SimpleNamespace] = {
            self.created_ticket.public_id: self.created_ticket,
        }
        if self.active_ticket is not None:
            self.tickets[self.active_ticket.public_id] = self.active_ticket

    async def create(
        self,
        *,
        client_chat_id: int,
        subject: str,
        priority: object = None,
    ) -> SimpleNamespace:
        self.create_calls.append(
            {
                "client_chat_id": client_chat_id,
                "subject": subject,
                "priority": priority,
            }
        )
        return self.created_ticket

    async def get_active_by_client_chat_id(self, client_chat_id: int) -> SimpleNamespace | None:
        self.active_lookup_calls.append(client_chat_id)
        return self.active_ticket

    async def get_by_public_id(self, public_id: UUID) -> SimpleNamespace | None:
        return self.tickets.get(public_id)

    async def enqueue(self, *, ticket_public_id: UUID) -> SimpleNamespace | None:
        self.enqueue_calls.append(ticket_public_id)
        ticket = self.tickets.get(ticket_public_id)
        if ticket is not None:
            ticket.status = TicketStatus.QUEUED
        return ticket

    async def assign_to_operator(
        self,
        *,
        ticket_public_id: UUID,
        operator_id: int,
    ) -> SimpleNamespace | None:
        self.assign_calls.append(
            {
                "ticket_public_id": ticket_public_id,
                "operator_id": operator_id,
            }
        )
        ticket = self.tickets.get(ticket_public_id)
        if ticket is not None:
            ticket.assigned_operator_id = operator_id
            ticket.status = TicketStatus.ASSIGNED
        return ticket

    async def escalate(self, *, ticket_public_id: UUID) -> SimpleNamespace | None:
        self.escalate_calls.append(ticket_public_id)
        ticket = self.tickets.get(ticket_public_id)
        if ticket is not None:
            ticket.status = TicketStatus.ESCALATED
        return ticket

    async def close(self, *, ticket_public_id: UUID) -> SimpleNamespace | None:
        self.close_calls.append(ticket_public_id)
        ticket = self.tickets.get(ticket_public_id)
        if ticket is not None:
            ticket.status = TicketStatus.CLOSED
            ticket.closed_at = object()
        return ticket

    async def count_by_status(self) -> dict[TicketStatus, int]:
        return self.by_status or {}


@dataclass
class StubTicketMessageRepository:
    added_messages: list[dict[str, object]]

    async def add(
        self,
        *,
        ticket_id: int,
        telegram_message_id: int,
        sender_type: TicketMessageSenderType,
        text: str,
        sender_operator_id: int | None = None,
    ) -> None:
        self.added_messages.append(
            {
                "ticket_id": ticket_id,
                "telegram_message_id": telegram_message_id,
                "sender_type": sender_type,
                "text": text,
                "sender_operator_id": sender_operator_id,
            }
        )


@dataclass
class StubTicketEventRepository:
    added_events: list[dict[str, object]]

    async def add(
        self,
        *,
        ticket_id: int,
        event_type: TicketEventType,
        payload_json: Mapping[str, object] | None = None,
    ) -> None:
        self.added_events.append(
            {
                "ticket_id": ticket_id,
                "event_type": event_type,
                "payload_json": dict(payload_json) if payload_json is not None else None,
            }
        )


@dataclass
class StubOperatorRepository:
    operator_ids: dict[int, int]

    def __post_init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def get_or_create(
        self,
        *,
        telegram_user_id: int,
        display_name: str,
        username: str | None = None,
    ) -> int:
        self.calls.append(
            {
                "telegram_user_id": telegram_user_id,
                "display_name": display_name,
                "username": username,
            }
        )
        return self.operator_ids[telegram_user_id]


def build_ticket(
    *,
    ticket_id: int,
    public_id: UUID,
    status: TicketStatus,
    assigned_operator_id: int | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=ticket_id,
        public_id=public_id,
        client_chat_id=123,
        status=status,
        priority="normal",
        subject="Need help",
        assigned_operator_id=assigned_operator_id,
        created_at=None,
        updated_at=None,
        first_response_at=None,
        closed_at=None,
    )


async def test_create_ticket_from_first_client_message_creates_queues_and_logs_events() -> None:
    public_id = uuid4()
    created_ticket = build_ticket(ticket_id=1, public_id=public_id, status=TicketStatus.NEW)
    ticket_repository = StubTicketRepository(created_ticket=created_ticket)
    message_repository = StubTicketMessageRepository(added_messages=[])
    event_repository = StubTicketEventRepository(added_events=[])
    service = HelpdeskService(
        ticket_repository=ticket_repository,
        ticket_message_repository=message_repository,
        ticket_event_repository=event_repository,
        operator_repository=StubOperatorRepository(operator_ids={}),
    )

    result = await service.create_ticket_from_client_message(
        client_chat_id=555,
        telegram_message_id=777,
        text="Cannot log in",
    )

    assert result.public_id == public_id
    assert result.public_number.startswith("HD-")
    assert result.status == TicketStatus.QUEUED
    assert result.created is True
    assert result.event_type == TicketEventType.QUEUED
    assert ticket_repository.create_calls[0]["client_chat_id"] == 555
    assert ticket_repository.enqueue_calls == [public_id]
    assert message_repository.added_messages[0]["sender_type"] == TicketMessageSenderType.CLIENT
    assert [event["event_type"] for event in event_repository.added_events] == [
        TicketEventType.CREATED,
        TicketEventType.QUEUED,
        TicketEventType.CLIENT_MESSAGE_ADDED,
    ]


async def test_follow_up_client_message_reuses_active_open_ticket() -> None:
    public_id = uuid4()
    active_ticket = build_ticket(ticket_id=2, public_id=public_id, status=TicketStatus.ASSIGNED)
    ticket_repository = StubTicketRepository(
        created_ticket=build_ticket(ticket_id=1, public_id=uuid4(), status=TicketStatus.NEW),
        active_ticket=active_ticket,
    )
    message_repository = StubTicketMessageRepository(added_messages=[])
    event_repository = StubTicketEventRepository(added_events=[])
    service = HelpdeskService(
        ticket_repository=ticket_repository,
        ticket_message_repository=message_repository,
        ticket_event_repository=event_repository,
        operator_repository=StubOperatorRepository(operator_ids={}),
    )

    result = await service.create_ticket_from_client_message(
        client_chat_id=active_ticket.client_chat_id,
        telegram_message_id=888,
        text="Any update?",
    )

    assert result.public_id == public_id
    assert result.status == TicketStatus.ASSIGNED
    assert result.created is False
    assert result.event_type == TicketEventType.CLIENT_MESSAGE_ADDED
    assert ticket_repository.create_calls == []
    assert message_repository.added_messages[0]["ticket_id"] == active_ticket.id
    assert [event["event_type"] for event in event_repository.added_events] == [
        TicketEventType.CLIENT_MESSAGE_ADDED,
    ]


async def test_add_operator_message_logs_event_and_sets_first_response_timestamp() -> None:
    public_id = uuid4()
    ticket = build_ticket(ticket_id=1, public_id=public_id, status=TicketStatus.ASSIGNED)
    ticket_repository = StubTicketRepository(created_ticket=ticket)
    message_repository = StubTicketMessageRepository(added_messages=[])
    event_repository = StubTicketEventRepository(added_events=[])
    service = HelpdeskService(
        ticket_repository=ticket_repository,
        ticket_message_repository=message_repository,
        ticket_event_repository=event_repository,
        operator_repository=StubOperatorRepository(operator_ids={}),
    )

    result = await service.add_message_to_ticket(
        ticket_public_id=public_id,
        telegram_message_id=999,
        sender_type=TicketMessageSenderType.OPERATOR,
        text="Please try again now.",
        sender_operator_id=42,
    )

    assert result is not None
    assert result.event_type == TicketEventType.OPERATOR_MESSAGE_ADDED
    assert ticket.first_response_at is not None
    assert message_repository.added_messages[0]["sender_operator_id"] == 42
    assert event_repository.added_events[0]["event_type"] == TicketEventType.OPERATOR_MESSAGE_ADDED


async def test_assign_and_reassign_ticket_create_distinct_events() -> None:
    public_id = uuid4()
    ticket = build_ticket(ticket_id=1, public_id=public_id, status=TicketStatus.QUEUED)
    ticket_repository = StubTicketRepository(created_ticket=ticket)
    event_repository = StubTicketEventRepository(added_events=[])
    operator_repository = StubOperatorRepository(operator_ids={1001: 7, 1002: 9})
    service = HelpdeskService(
        ticket_repository=ticket_repository,
        ticket_message_repository=StubTicketMessageRepository(added_messages=[]),
        ticket_event_repository=event_repository,
        operator_repository=operator_repository,
    )

    first_result = await service.assign_ticket_to_operator(
        ticket_public_id=public_id,
        telegram_user_id=1001,
        display_name="Operator One",
    )
    second_result = await service.assign_ticket_to_operator(
        ticket_public_id=public_id,
        telegram_user_id=1002,
        display_name="Operator Two",
    )

    assert first_result is not None
    assert second_result is not None
    assert first_result.event_type == TicketEventType.ASSIGNED
    assert second_result.event_type == TicketEventType.REASSIGNED
    assert ticket.assigned_operator_id == 9
    assert [event["event_type"] for event in event_repository.added_events] == [
        TicketEventType.ASSIGNED,
        TicketEventType.REASSIGNED,
    ]


async def test_escalate_and_close_ticket_log_workflow_events() -> None:
    public_id = uuid4()
    ticket = build_ticket(ticket_id=1, public_id=public_id, status=TicketStatus.ASSIGNED)
    ticket_repository = StubTicketRepository(created_ticket=ticket)
    event_repository = StubTicketEventRepository(added_events=[])
    service = HelpdeskService(
        ticket_repository=ticket_repository,
        ticket_message_repository=StubTicketMessageRepository(added_messages=[]),
        ticket_event_repository=event_repository,
        operator_repository=StubOperatorRepository(operator_ids={}),
    )

    escalated = await service.escalate_ticket(ticket_public_id=public_id)
    closed = await service.close_ticket(ticket_public_id=public_id)

    assert escalated is not None
    assert closed is not None
    assert escalated.status == TicketStatus.ESCALATED
    assert closed.status == TicketStatus.CLOSED
    assert [event["event_type"] for event in event_repository.added_events] == [
        TicketEventType.ESCALATED,
        TicketEventType.CLOSED,
    ]


async def test_invalid_transition_is_rejected() -> None:
    public_id = uuid4()
    closed_ticket = build_ticket(ticket_id=1, public_id=public_id, status=TicketStatus.CLOSED)
    ticket_repository = StubTicketRepository(created_ticket=closed_ticket)
    service = HelpdeskService(
        ticket_repository=ticket_repository,
        ticket_message_repository=StubTicketMessageRepository(added_messages=[]),
        ticket_event_repository=StubTicketEventRepository(added_events=[]),
        operator_repository=StubOperatorRepository(operator_ids={1001: 7}),
    )

    with pytest.raises(InvalidTicketTransitionError):
        await service.assign_ticket_to_operator(
            ticket_public_id=public_id,
            telegram_user_id=1001,
            display_name="Operator One",
        )


async def test_get_basic_stats_returns_aggregated_totals() -> None:
    ticket_repository = StubTicketRepository(
        created_ticket=build_ticket(ticket_id=1, public_id=uuid4(), status=TicketStatus.NEW),
        by_status={
            TicketStatus.NEW: 2,
            TicketStatus.ASSIGNED: 3,
            TicketStatus.CLOSED: 1,
        },
    )
    service = HelpdeskService(
        ticket_repository=ticket_repository,
        ticket_message_repository=StubTicketMessageRepository(added_messages=[]),
        ticket_event_repository=StubTicketEventRepository(added_events=[]),
        operator_repository=StubOperatorRepository(operator_ids={}),
    )

    stats = await service.get_basic_stats()

    assert stats.total == 6
    assert stats.open_total == 5
    assert stats.by_status[TicketStatus.CLOSED] == 1
