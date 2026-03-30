from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from domain.enums.tickets import (
    TicketEventType,
    TicketMessageSenderType,
    TicketPriority,
    TicketStatus,
)
from infrastructure.db.models import Macro, Tag, Ticket, TicketEvent, TicketTag
from infrastructure.db.repositories import (
    SqlAlchemyMacroRepository,
    SqlAlchemyTagRepository,
    SqlAlchemyTicketEventRepository,
    SqlAlchemyTicketMessageRepository,
    SqlAlchemyTicketRepository,
    SqlAlchemyTicketTagRepository,
)


@dataclass
class FakeResult:
    scalar: Any = None
    rows: list[tuple[Any, Any]] = field(default_factory=list)
    scalar_items: list[Any] = field(default_factory=list)

    def scalar_one_or_none(self) -> Any:
        return self.scalar

    def all(self) -> list[Any]:
        if self.scalar_items:
            return self.scalar_items
        return self.rows

    def scalars(self) -> FakeResult:
        return self

    def first(self) -> Any:
        if self.scalar_items:
            return self.scalar_items[0]
        if self.rows:
            return self.rows[0]
        return None


@dataclass
class FakeAsyncSession:
    result: FakeResult = field(default_factory=FakeResult)
    queued_results: list[FakeResult] = field(default_factory=list)
    added: list[Any] = field(default_factory=list)
    deleted: list[Any] = field(default_factory=list)
    flush_count: int = 0
    executed_statements: list[Any] = field(default_factory=list)

    def add(self, value: Any) -> None:
        self.added.append(value)

    async def delete(self, value: Any) -> None:
        self.deleted.append(value)

    async def flush(self) -> None:
        self.flush_count += 1

    async def execute(self, statement: Any) -> FakeResult:
        self.executed_statements.append(statement)
        if self.queued_results:
            return self.queued_results.pop(0)
        return self.result


async def test_create_adds_ticket_to_session() -> None:
    session = FakeAsyncSession()
    repository = SqlAlchemyTicketRepository(cast(AsyncSession, session))

    ticket = await repository.create(
        client_chat_id=100,
        subject="Need access",
        priority=TicketPriority.NORMAL,
    )

    assert session.added == [cast(object, ticket)]
    assert session.flush_count == 1
    assert ticket.client_chat_id == 100
    assert ticket.subject == "Need access"
    assert ticket.status == TicketStatus.NEW


async def test_enqueue_updates_ticket_status() -> None:
    ticket = Ticket(
        client_chat_id=100,
        subject="Need access",
        priority=TicketPriority.NORMAL,
        public_id=uuid4(),
    )
    session = FakeAsyncSession(result=FakeResult(scalar=ticket))
    repository = SqlAlchemyTicketRepository(cast(AsyncSession, session))

    result = await repository.enqueue(ticket_public_id=ticket.public_id)

    assert cast(object, result) is ticket
    assert ticket.status == TicketStatus.QUEUED
    assert session.flush_count == 1


async def test_assign_queued_to_operator_only_updates_queued_tickets() -> None:
    ticket = Ticket(
        client_chat_id=100,
        subject="Need access",
        priority=TicketPriority.NORMAL,
        public_id=uuid4(),
        status=TicketStatus.ASSIGNED,
    )
    session = FakeAsyncSession(result=FakeResult(scalar=ticket))
    repository = SqlAlchemyTicketRepository(cast(AsyncSession, session))

    result = await repository.assign_queued_to_operator(
        ticket_public_id=ticket.public_id,
        operator_id=77,
    )

    assert cast(object, result) is None
    assert ticket.status == TicketStatus.ASSIGNED
    assert session.flush_count == 0


async def test_assign_to_operator_updates_ticket_status() -> None:
    ticket = Ticket(
        client_chat_id=100,
        subject="Need access",
        priority=TicketPriority.NORMAL,
        public_id=uuid4(),
    )
    session = FakeAsyncSession(result=FakeResult(scalar=ticket))
    repository = SqlAlchemyTicketRepository(cast(AsyncSession, session))

    result = await repository.assign_to_operator(
        ticket_public_id=ticket.public_id,
        operator_id=77,
    )

    assert cast(object, result) is ticket
    assert ticket.assigned_operator_id == 77
    assert ticket.status == TicketStatus.ASSIGNED
    assert session.flush_count == 1


async def test_escalate_updates_ticket_status() -> None:
    ticket = Ticket(
        client_chat_id=100,
        subject="Need access",
        priority=TicketPriority.NORMAL,
        public_id=uuid4(),
    )
    session = FakeAsyncSession(result=FakeResult(scalar=ticket))
    repository = SqlAlchemyTicketRepository(cast(AsyncSession, session))

    result = await repository.escalate(ticket_public_id=ticket.public_id)

    assert cast(object, result) is ticket
    assert ticket.status == TicketStatus.ESCALATED
    assert session.flush_count == 1


async def test_close_sets_closed_status_and_timestamp() -> None:
    ticket = Ticket(
        client_chat_id=100,
        subject="Need access",
        priority=TicketPriority.NORMAL,
        public_id=uuid4(),
    )
    session = FakeAsyncSession(result=FakeResult(scalar=ticket))
    repository = SqlAlchemyTicketRepository(cast(AsyncSession, session))

    result = await repository.close(ticket_public_id=ticket.public_id)

    assert cast(object, result) is ticket
    assert ticket.status == TicketStatus.CLOSED
    assert ticket.closed_at is not None
    assert session.flush_count == 1


async def test_count_by_status_returns_mapping() -> None:
    session = FakeAsyncSession(
        result=FakeResult(
            rows=[
                (TicketStatus.NEW, 2),
                (TicketStatus.CLOSED, 1),
            ]
        )
    )
    repository = SqlAlchemyTicketRepository(cast(AsyncSession, session))

    result = await repository.count_by_status()

    assert result == {
        TicketStatus.NEW: 2,
        TicketStatus.CLOSED: 1,
    }


async def test_get_details_by_public_id_returns_enriched_ticket_view_with_tags() -> None:
    ticket = Ticket(
        client_chat_id=100,
        subject="Need access",
        priority=TicketPriority.NORMAL,
        public_id=uuid4(),
        status=TicketStatus.ASSIGNED,
        assigned_operator_id=77,
    )
    ticket.id = 1
    session = FakeAsyncSession(
        queued_results=[
            FakeResult(scalar=ticket),
            FakeResult(scalar="Operator One"),
            FakeResult(rows=[("Latest client message", TicketMessageSenderType.CLIENT)]),
            FakeResult(scalar_items=["billing", "vip"]),
        ]
    )
    repository = SqlAlchemyTicketRepository(cast(AsyncSession, session))

    result = await repository.get_details_by_public_id(ticket.public_id)

    assert result is not None
    assert result.public_id == ticket.public_id
    assert result.assigned_operator_name == "Operator One"
    assert result.last_message_text == "Latest client message"
    assert result.tags == ("billing", "vip")


async def test_get_next_queued_ticket_returns_first_matching_ticket() -> None:
    first_ticket = Ticket(
        client_chat_id=100,
        subject="First",
        priority=TicketPriority.NORMAL,
        public_id=uuid4(),
        status=TicketStatus.QUEUED,
    )
    session = FakeAsyncSession(result=FakeResult(scalar=first_ticket))
    repository = SqlAlchemyTicketRepository(cast(AsyncSession, session))

    result = await repository.get_next_queued_ticket()

    assert cast(object, result) is first_ticket


async def test_list_queued_tickets_returns_ordered_sequence() -> None:
    first_ticket = Ticket(
        client_chat_id=100,
        subject="First",
        priority=TicketPriority.NORMAL,
        public_id=uuid4(),
        status=TicketStatus.QUEUED,
    )
    second_ticket = Ticket(
        client_chat_id=101,
        subject="Second",
        priority=TicketPriority.HIGH,
        public_id=uuid4(),
        status=TicketStatus.QUEUED,
    )
    session = FakeAsyncSession(result=FakeResult(scalar_items=[first_ticket, second_ticket]))
    repository = SqlAlchemyTicketRepository(cast(AsyncSession, session))

    result = await repository.list_queued_tickets(limit=2)

    assert [ticket.subject for ticket in result] == ["First", "Second"]


async def test_ticket_message_repository_allocates_negative_internal_ids() -> None:
    session = FakeAsyncSession(result=FakeResult(scalar=-4))
    repository = SqlAlchemyTicketMessageRepository(cast(AsyncSession, session))

    result = await repository.allocate_internal_telegram_message_id(
        ticket_id=10,
        sender_type=TicketMessageSenderType.OPERATOR,
    )

    assert result == -5


async def test_ticket_event_repository_persists_event_rows() -> None:
    session = FakeAsyncSession()
    repository = SqlAlchemyTicketEventRepository(cast(AsyncSession, session))

    await repository.add(
        ticket_id=10,
        event_type=TicketEventType.QUEUED,
        payload_json={"from_status": "new", "to_status": "queued"},
    )

    assert len(session.added) == 1
    event = cast(TicketEvent, session.added[0])
    assert event.ticket_id == 10
    assert event.event_type == TicketEventType.QUEUED
    assert event.payload_json == {"from_status": "new", "to_status": "queued"}
    assert session.flush_count == 1


async def test_macro_repository_lists_and_fetches_macros() -> None:
    first_macro = Macro(title="First", body="Hello")
    first_macro.id = 1
    second_macro = Macro(title="Second", body="World")
    second_macro.id = 2
    session = FakeAsyncSession(
        queued_results=[
            FakeResult(scalar_items=[first_macro, second_macro]),
            FakeResult(scalar=second_macro),
        ]
    )
    repository = SqlAlchemyMacroRepository(cast(AsyncSession, session))

    listed = await repository.list_all()
    fetched = await repository.get_by_id(macro_id=2)

    assert [macro.title for macro in listed] == ["First", "Second"]
    assert fetched is second_macro


async def test_tag_repository_normalizes_and_lists_tags() -> None:
    existing_tag = Tag(name="vip")
    existing_tag.id = 3
    session = FakeAsyncSession(
        queued_results=[
            FakeResult(scalar=existing_tag),
            FakeResult(scalar=existing_tag),
            FakeResult(scalar_items=[existing_tag]),
        ]
    )
    repository = SqlAlchemyTagRepository(cast(AsyncSession, session))

    created_id = await repository.get_or_create(name=" VIP ")
    fetched = await repository.get_by_name(name="vip")
    listed = await repository.list_all()

    assert created_id == 3
    assert fetched is existing_tag
    assert listed == [existing_tag]


async def test_ticket_tag_repository_add_remove_and_list_links() -> None:
    first_tag = Tag(name="billing")
    first_tag.id = 10
    existing_link = TicketTag(ticket_id=5, tag_id=10)
    session = FakeAsyncSession(
        queued_results=[
            FakeResult(scalar=None),
            FakeResult(scalar=existing_link),
            FakeResult(scalar_items=[first_tag]),
        ]
    )
    repository = SqlAlchemyTicketTagRepository(cast(AsyncSession, session))

    added = await repository.add(ticket_id=5, tag_id=10)
    removed = await repository.remove(ticket_id=5, tag_id=10)
    listed = await repository.list_for_ticket(ticket_id=5)

    assert added is True
    assert removed is True
    assert listed == [first_tag]
    assert isinstance(session.added[0], TicketTag)
    assert session.deleted == [existing_link]
