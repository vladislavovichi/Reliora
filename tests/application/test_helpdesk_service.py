from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

from application.services.helpdesk import HelpdeskService
from domain.entities.ticket import TicketDetails
from domain.enums.tickets import (
    TicketEventType,
    TicketMessageSenderType,
    TicketPriority,
    TicketStatus,
)


def normalize_tag_name(name: str) -> str:
    return " ".join(name.strip().lower().split())


@dataclass
class StubTicketRepository:
    created_ticket: SimpleNamespace
    active_ticket: SimpleNamespace | None = None
    queued_tickets: list[SimpleNamespace] | None = None
    by_status: dict[TicketStatus, int] | None = None

    def __post_init__(self) -> None:
        self.create_calls: list[dict[str, object]] = []
        self.active_lookup_calls: list[int] = []
        self.next_queued_calls: list[bool] = []
        self.list_queued_calls: list[dict[str, object]] = []
        self.enqueue_calls: list[UUID] = []
        self.assign_queued_calls: list[dict[str, object]] = []
        self.assign_calls: list[dict[str, object]] = []
        self.escalate_calls: list[UUID] = []
        self.close_calls: list[UUID] = []
        self.tickets: dict[UUID, SimpleNamespace] = {
            self.created_ticket.public_id: self.created_ticket,
        }
        if self.active_ticket is not None:
            self.tickets[self.active_ticket.public_id] = self.active_ticket
        if self.queued_tickets is None:
            self.queued_tickets = []
        for ticket in self.queued_tickets:
            self.tickets[ticket.public_id] = ticket

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

    async def get_details_by_public_id(self, public_id: UUID) -> TicketDetails | None:
        ticket = self.tickets.get(public_id)
        if ticket is None or ticket.id is None:
            return None

        return TicketDetails(
            id=ticket.id,
            public_id=ticket.public_id,
            client_chat_id=ticket.client_chat_id,
            status=ticket.status,
            priority=ticket.priority,
            subject=ticket.subject,
            assigned_operator_id=ticket.assigned_operator_id,
            assigned_operator_name=getattr(ticket, "assigned_operator_name", None),
            created_at=ticket.created_at,
            updated_at=ticket.updated_at,
            first_response_at=ticket.first_response_at,
            closed_at=ticket.closed_at,
            tags=tuple(getattr(ticket, "tags", ())),
            last_message_text=getattr(ticket, "last_message_text", None),
            last_message_sender_type=getattr(ticket, "last_message_sender_type", None),
        )

    async def get_next_queued_ticket(
        self, *, prioritize_priority: bool = False
    ) -> SimpleNamespace | None:
        self.next_queued_calls.append(prioritize_priority)
        for ticket in self.queued_tickets or []:
            if ticket.status == TicketStatus.QUEUED:
                return ticket
        return None

    async def list_queued_tickets(
        self,
        *,
        limit: int | None = None,
        prioritize_priority: bool = False,
    ) -> list[SimpleNamespace]:
        self.list_queued_calls.append(
            {
                "limit": limit,
                "prioritize_priority": prioritize_priority,
            }
        )
        tickets = [
            ticket
            for ticket in self.queued_tickets or []
            if ticket.status == TicketStatus.QUEUED
        ]
        if limit is None:
            return tickets
        return tickets[:limit]

    async def list_open_tickets(self, *, limit: int | None = None) -> list[SimpleNamespace]:
        tickets = [
            ticket
            for ticket in self.tickets.values()
            if ticket.status != TicketStatus.CLOSED
        ]
        tickets.sort(key=lambda ticket: (ticket.updated_at, ticket.id))
        if limit is None:
            return tickets
        return tickets[:limit]

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

    async def assign_queued_to_operator(
        self,
        *,
        ticket_public_id: UUID,
        operator_id: int,
    ) -> SimpleNamespace | None:
        self.assign_queued_calls.append(
            {
                "ticket_public_id": ticket_public_id,
                "operator_id": operator_id,
            }
        )
        ticket = self.tickets.get(ticket_public_id)
        if ticket is None or ticket.status != TicketStatus.QUEUED:
            return None

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
    next_internal_message_id: int = -1

    def __post_init__(self) -> None:
        self.allocated_internal_ids: list[dict[str, object]] = []

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

    async def allocate_internal_telegram_message_id(
        self,
        *,
        ticket_id: int,
        sender_type: TicketMessageSenderType,
    ) -> int:
        self.allocated_internal_ids.append(
            {
                "ticket_id": ticket_id,
                "sender_type": sender_type,
            }
        )
        return self.next_internal_message_id


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

    async def exists(self, *, ticket_id: int, event_type: TicketEventType) -> bool:
        return any(
            event["ticket_id"] == ticket_id and event["event_type"] == event_type
            for event in self.added_events
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


@dataclass
class StubMacroRepository:
    macros: list[SimpleNamespace] = field(default_factory=list)

    async def list_all(self) -> list[SimpleNamespace]:
        return sorted(self.macros, key=lambda macro: (macro.title, macro.id))

    async def get_by_id(self, *, macro_id: int) -> SimpleNamespace | None:
        for macro in self.macros:
            if macro.id == macro_id:
                return macro
        return None


@dataclass
class StubSLAPolicyRepository:
    policies: dict[TicketPriority | None, SimpleNamespace]

    def __post_init__(self) -> None:
        self.calls: list[TicketPriority] = []

    async def get_for_priority(
        self, *, priority: TicketPriority
    ) -> SimpleNamespace | None:
        self.calls.append(priority)
        return self.policies.get(priority) or self.policies.get(None)


@dataclass
class StubTagRepository:
    initial_tags: list[tuple[int, str]] = field(default_factory=list)
    next_id: int = 100

    def __post_init__(self) -> None:
        self.records_by_name: dict[str, SimpleNamespace] = {}
        self.records_by_id: dict[int, SimpleNamespace] = {}
        for tag_id, name in self.initial_tags:
            normalized = normalize_tag_name(name)
            record = SimpleNamespace(id=tag_id, name=normalized)
            self.records_by_name[normalized] = record
            self.records_by_id[tag_id] = record
            self.next_id = max(self.next_id, tag_id + 1)

    async def get_or_create(self, *, name: str) -> int:
        normalized = normalize_tag_name(name)
        record = self.records_by_name.get(normalized)
        if record is None:
            record = SimpleNamespace(id=self.next_id, name=normalized)
            self.records_by_name[normalized] = record
            self.records_by_id[record.id] = record
            self.next_id += 1
        return record.id

    async def get_by_name(self, *, name: str) -> SimpleNamespace | None:
        return self.records_by_name.get(normalize_tag_name(name))

    async def list_all(self) -> list[SimpleNamespace]:
        return sorted(
            self.records_by_name.values(),
            key=lambda tag: (tag.name, tag.id),
        )


@dataclass
class StubTicketTagRepository:
    tag_repository: StubTagRepository
    ticket_tag_ids: dict[int, set[int]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.add_calls: list[dict[str, int]] = []
        self.remove_calls: list[dict[str, int]] = []

    async def list_for_ticket(self, *, ticket_id: int) -> list[SimpleNamespace]:
        tag_ids = self.ticket_tag_ids.get(ticket_id, set())
        return [
            tag
            for tag in sorted(
                self.tag_repository.records_by_id.values(),
                key=lambda item: (item.name, item.id),
            )
            if tag.id in tag_ids
        ]

    async def add(self, *, ticket_id: int, tag_id: int) -> bool:
        self.add_calls.append({"ticket_id": ticket_id, "tag_id": tag_id})
        tag_ids = self.ticket_tag_ids.setdefault(ticket_id, set())
        if tag_id in tag_ids:
            return False
        tag_ids.add(tag_id)
        return True

    async def remove(self, *, ticket_id: int, tag_id: int) -> bool:
        self.remove_calls.append({"ticket_id": ticket_id, "tag_id": tag_id})
        tag_ids = self.ticket_tag_ids.setdefault(ticket_id, set())
        if tag_id not in tag_ids:
            return False
        tag_ids.remove(tag_id)
        return True


def build_ticket(
    *,
    ticket_id: int,
    public_id: UUID,
    status: TicketStatus,
    assigned_operator_id: int | None = None,
    assigned_operator_name: str | None = None,
    last_message_text: str | None = None,
    last_message_sender_type: TicketMessageSenderType | None = None,
    tags: tuple[str, ...] = (),
    priority: TicketPriority = TicketPriority.NORMAL,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
    first_response_at: datetime | None = None,
    closed_at: datetime | None = None,
) -> SimpleNamespace:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=ticket_id,
        public_id=public_id,
        client_chat_id=123,
        status=status,
        priority=priority,
        subject="Need help",
        assigned_operator_id=assigned_operator_id,
        created_at=created_at or now,
        updated_at=updated_at or now,
        first_response_at=first_response_at,
        closed_at=closed_at,
        assigned_operator_name=assigned_operator_name,
        last_message_text=last_message_text,
        last_message_sender_type=last_message_sender_type,
        tags=tags,
    )


def build_service(
    *,
    ticket_repository: StubTicketRepository,
    message_repository: StubTicketMessageRepository | None = None,
    event_repository: StubTicketEventRepository | None = None,
    operator_repository: StubOperatorRepository | None = None,
    macro_repository: StubMacroRepository | None = None,
    sla_policy_repository: StubSLAPolicyRepository | None = None,
    tag_repository: StubTagRepository | None = None,
    ticket_tag_repository: StubTicketTagRepository | None = None,
) -> HelpdeskService:
    active_tag_repository = tag_repository or StubTagRepository()
    return HelpdeskService(
        ticket_repository=ticket_repository,
        ticket_message_repository=message_repository
        or StubTicketMessageRepository(added_messages=[]),
        ticket_event_repository=event_repository or StubTicketEventRepository(added_events=[]),
        operator_repository=operator_repository or StubOperatorRepository(operator_ids={}),
        macro_repository=macro_repository or StubMacroRepository(),
        sla_policy_repository=sla_policy_repository
        or StubSLAPolicyRepository(
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
        tag_repository=active_tag_repository,
        ticket_tag_repository=ticket_tag_repository
        or StubTicketTagRepository(tag_repository=active_tag_repository),
    )


async def test_create_ticket_from_first_client_message_creates_queues_and_logs_events() -> None:
    public_id = uuid4()
    created_ticket = build_ticket(ticket_id=1, public_id=public_id, status=TicketStatus.NEW)
    ticket_repository = StubTicketRepository(created_ticket=created_ticket)
    message_repository = StubTicketMessageRepository(added_messages=[])
    event_repository = StubTicketEventRepository(added_events=[])
    service = build_service(
        ticket_repository=ticket_repository,
        message_repository=message_repository,
        event_repository=event_repository,
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
    service = build_service(
        ticket_repository=ticket_repository,
        message_repository=message_repository,
        event_repository=event_repository,
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
    message_repository = StubTicketMessageRepository(added_messages=[])
    event_repository = StubTicketEventRepository(added_events=[])
    service = build_service(
        ticket_repository=StubTicketRepository(created_ticket=ticket),
        message_repository=message_repository,
        event_repository=event_repository,
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
    event_repository = StubTicketEventRepository(added_events=[])
    operator_repository = StubOperatorRepository(operator_ids={1001: 7, 1002: 9})
    service = build_service(
        ticket_repository=StubTicketRepository(created_ticket=ticket),
        event_repository=event_repository,
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


async def test_get_and_list_queued_tickets_follow_queue_order() -> None:
    first_ticket = build_ticket(ticket_id=1, public_id=uuid4(), status=TicketStatus.QUEUED)
    second_ticket = build_ticket(ticket_id=2, public_id=uuid4(), status=TicketStatus.QUEUED)
    service = build_service(
        ticket_repository=StubTicketRepository(
            created_ticket=build_ticket(ticket_id=3, public_id=uuid4(), status=TicketStatus.NEW),
            queued_tickets=[first_ticket, second_ticket],
        )
    )

    next_ticket = await service.get_next_queued_ticket()
    queued_tickets = await service.list_queued_tickets(limit=1)

    assert next_ticket is not None
    assert next_ticket.public_id == first_ticket.public_id
    assert next_ticket.public_number.startswith("HD-")
    assert queued_tickets[0].public_id == first_ticket.public_id


async def test_assign_next_ticket_to_operator_assigns_oldest_queued_ticket() -> None:
    first_ticket = build_ticket(ticket_id=1, public_id=uuid4(), status=TicketStatus.QUEUED)
    second_ticket = build_ticket(ticket_id=2, public_id=uuid4(), status=TicketStatus.QUEUED)
    event_repository = StubTicketEventRepository(added_events=[])
    service = build_service(
        ticket_repository=StubTicketRepository(
            created_ticket=build_ticket(ticket_id=3, public_id=uuid4(), status=TicketStatus.NEW),
            queued_tickets=[first_ticket, second_ticket],
        ),
        event_repository=event_repository,
        operator_repository=StubOperatorRepository(operator_ids={1001: 7}),
    )

    result = await service.assign_next_ticket_to_operator(
        telegram_user_id=1001,
        display_name="Operator One",
    )

    assert result is not None
    assert result.public_id == first_ticket.public_id
    assert result.status == TicketStatus.ASSIGNED
    assert first_ticket.assigned_operator_id == 7
    assert event_repository.added_events[0]["event_type"] == TicketEventType.ASSIGNED


async def test_get_ticket_details_returns_operator_facing_summary_with_tags() -> None:
    public_id = uuid4()
    ticket = build_ticket(
        ticket_id=1,
        public_id=public_id,
        status=TicketStatus.ASSIGNED,
        assigned_operator_id=7,
        assigned_operator_name="Operator One",
        last_message_text="Client says hello",
        last_message_sender_type=TicketMessageSenderType.CLIENT,
        tags=("billing", "vip"),
    )
    service = build_service(ticket_repository=StubTicketRepository(created_ticket=ticket))

    result = await service.get_ticket_details(ticket_public_id=public_id)

    assert result is not None
    assert result.public_id == public_id
    assert result.public_number.startswith("HD-")
    assert result.assigned_operator_name == "Operator One"
    assert result.last_message_text == "Client says hello"
    assert result.last_message_sender_type == TicketMessageSenderType.CLIENT
    assert result.tags == ("billing", "vip")


async def test_reply_to_ticket_as_operator_persists_message_and_returns_client_chat() -> None:
    public_id = uuid4()
    ticket = build_ticket(
        ticket_id=1,
        public_id=public_id,
        status=TicketStatus.ASSIGNED,
        assigned_operator_id=7,
    )
    message_repository = StubTicketMessageRepository(added_messages=[])
    event_repository = StubTicketEventRepository(added_events=[])
    service = build_service(
        ticket_repository=StubTicketRepository(created_ticket=ticket),
        message_repository=message_repository,
        event_repository=event_repository,
        operator_repository=StubOperatorRepository(operator_ids={1001: 7}),
    )

    result = await service.reply_to_ticket_as_operator(
        ticket_public_id=public_id,
        telegram_user_id=1001,
        display_name="Operator One",
        username="operator_one",
        telegram_message_id=4321,
        text="Please try again now.",
    )

    assert result is not None
    assert result.client_chat_id == ticket.client_chat_id
    assert result.ticket.public_id == public_id
    assert message_repository.added_messages[0]["telegram_message_id"] == 4321
    assert event_repository.added_events[0]["event_type"] == TicketEventType.OPERATOR_MESSAGE_ADDED


async def test_list_macros_returns_sorted_operator_templates() -> None:
    service = build_service(
        ticket_repository=StubTicketRepository(
            created_ticket=build_ticket(ticket_id=1, public_id=uuid4(), status=TicketStatus.NEW)
        ),
        macro_repository=StubMacroRepository(
            macros=[
                SimpleNamespace(id=2, title="Z macro", body="Second"),
                SimpleNamespace(id=1, title="A macro", body="First"),
            ]
        ),
    )

    result = await service.list_macros()

    assert [(macro.id, macro.title) for macro in result] == [
        (1, "A macro"),
        (2, "Z macro"),
    ]


async def test_apply_macro_to_ticket_persists_operator_message_and_macro_event_payload() -> None:
    public_id = uuid4()
    ticket = build_ticket(
        ticket_id=1,
        public_id=public_id,
        status=TicketStatus.ASSIGNED,
        assigned_operator_id=7,
    )
    message_repository = StubTicketMessageRepository(
        added_messages=[],
        next_internal_message_id=-11,
    )
    event_repository = StubTicketEventRepository(added_events=[])
    service = build_service(
        ticket_repository=StubTicketRepository(created_ticket=ticket),
        message_repository=message_repository,
        event_repository=event_repository,
        operator_repository=StubOperatorRepository(operator_ids={1001: 7}),
        macro_repository=StubMacroRepository(
            macros=[SimpleNamespace(id=5, title="Resolved", body="Issue resolved.")]
        ),
    )

    result = await service.apply_macro_to_ticket(
        ticket_public_id=public_id,
        macro_id=5,
        telegram_user_id=1001,
        display_name="Operator One",
        username="operator_one",
    )

    assert result is not None
    assert result.client_chat_id == ticket.client_chat_id
    assert result.macro.id == 5
    assert result.macro.body == "Issue resolved."
    assert message_repository.allocated_internal_ids == [
        {
            "ticket_id": 1,
            "sender_type": TicketMessageSenderType.OPERATOR,
        }
    ]
    assert message_repository.added_messages[0]["telegram_message_id"] == -11
    assert message_repository.added_messages[0]["text"] == "Issue resolved."
    assert event_repository.added_events[0]["event_type"] == TicketEventType.OPERATOR_MESSAGE_ADDED
    assert event_repository.added_events[0]["payload_json"]["macro_id"] == 5
    assert event_repository.added_events[0]["payload_json"]["macro_title"] == "Resolved"


async def test_add_tag_to_ticket_is_idempotent_and_logs_event_once() -> None:
    public_id = uuid4()
    ticket = build_ticket(ticket_id=1, public_id=public_id, status=TicketStatus.ASSIGNED)
    tag_repository = StubTagRepository(initial_tags=[(10, "vip")])
    ticket_tag_repository = StubTicketTagRepository(tag_repository=tag_repository)
    event_repository = StubTicketEventRepository(added_events=[])
    service = build_service(
        ticket_repository=StubTicketRepository(created_ticket=ticket),
        event_repository=event_repository,
        tag_repository=tag_repository,
        ticket_tag_repository=ticket_tag_repository,
    )

    first_result = await service.add_tag_to_ticket(
        ticket_public_id=public_id,
        tag_name="VIP",
    )
    second_result = await service.add_tag_to_ticket(
        ticket_public_id=public_id,
        tag_name="vip",
    )

    assert first_result is not None
    assert second_result is not None
    assert first_result.changed is True
    assert second_result.changed is False
    assert first_result.tags == ("vip",)
    assert second_result.tags == ("vip",)
    assert [event["event_type"] for event in event_repository.added_events] == [
        TicketEventType.TAG_ADDED,
    ]


async def test_remove_tag_from_ticket_updates_links_and_logs_event() -> None:
    public_id = uuid4()
    ticket = build_ticket(ticket_id=1, public_id=public_id, status=TicketStatus.ASSIGNED)
    tag_repository = StubTagRepository(initial_tags=[(10, "vip"), (11, "billing")])
    ticket_tag_repository = StubTicketTagRepository(
        tag_repository=tag_repository,
        ticket_tag_ids={1: {10, 11}},
    )
    event_repository = StubTicketEventRepository(added_events=[])
    service = build_service(
        ticket_repository=StubTicketRepository(created_ticket=ticket),
        event_repository=event_repository,
        tag_repository=tag_repository,
        ticket_tag_repository=ticket_tag_repository,
    )

    result = await service.remove_tag_from_ticket(
        ticket_public_id=public_id,
        tag_name="VIP",
    )

    assert result is not None
    assert result.changed is True
    assert result.tag == "vip"
    assert result.tags == ("billing",)
    assert [event["event_type"] for event in event_repository.added_events] == [
        TicketEventType.TAG_REMOVED,
    ]


async def test_list_ticket_tags_and_available_tags_return_normalized_names() -> None:
    public_id = uuid4()
    ticket = build_ticket(ticket_id=1, public_id=public_id, status=TicketStatus.ASSIGNED)
    tag_repository = StubTagRepository(initial_tags=[(10, "vip"), (11, "billing")])
    ticket_tag_repository = StubTicketTagRepository(
        tag_repository=tag_repository,
        ticket_tag_ids={1: {11}},
    )
    service = build_service(
        ticket_repository=StubTicketRepository(created_ticket=ticket),
        tag_repository=tag_repository,
        ticket_tag_repository=ticket_tag_repository,
    )

    ticket_tags = await service.list_ticket_tags(ticket_public_id=public_id)
    available_tags = await service.list_available_tags()

    assert ticket_tags is not None
    assert ticket_tags.tags == ("billing",)
    assert available_tags == ["billing", "vip"]


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
        sla_policy_repository=StubSLAPolicyRepository(
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
    event_repository = StubTicketEventRepository(added_events=[])
    service = build_service(
        ticket_repository=StubTicketRepository(created_ticket=ticket),
        event_repository=event_repository,
        sla_policy_repository=StubSLAPolicyRepository(
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
    event_repository = StubTicketEventRepository(added_events=[])
    service = build_service(
        ticket_repository=StubTicketRepository(created_ticket=ticket),
        event_repository=event_repository,
        operator_repository=StubOperatorRepository(operator_ids={1002: 9}),
        sla_policy_repository=StubSLAPolicyRepository(
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
    event_repository = StubTicketEventRepository(added_events=[])
    service = build_service(
        ticket_repository=ticket_repository,
        event_repository=event_repository,
        operator_repository=StubOperatorRepository(operator_ids={2001: 11}),
        sla_policy_repository=StubSLAPolicyRepository(
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
            SimpleNamespace(
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
