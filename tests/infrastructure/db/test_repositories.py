from __future__ import annotations

from typing import Any, cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from domain.enums.tickets import (
    TicketEventType,
    TicketMessageSenderType,
    TicketPriority,
    TicketStatus,
)
from infrastructure.db.models import Macro, SLAPolicy, Tag, Ticket, TicketEvent, TicketTag
from infrastructure.db.repositories import (
    SqlAlchemyMacroRepository,
    SqlAlchemyOperatorRepository,
    SqlAlchemySLAPolicyRepository,
    SqlAlchemyTagRepository,
    SqlAlchemyTicketEventRepository,
    SqlAlchemyTicketMessageRepository,
    SqlAlchemyTicketRepository,
    SqlAlchemyTicketTagRepository,
)


def build_result(
    *,
    scalar: Any = None,
    rows: list[tuple[Any, ...]] | None = None,
    scalar_items: list[Any] | None = None,
) -> Mock:
    result = Mock()
    active_rows = [] if rows is None else rows
    active_scalar_items = [] if scalar_items is None else scalar_items
    result.scalar_one_or_none.return_value = scalar
    result.all.return_value = active_scalar_items if active_scalar_items else active_rows

    scalars_result = Mock()
    scalars_result.all.return_value = active_scalar_items
    result.scalars.return_value = scalars_result
    result.first.return_value = (
        active_scalar_items[0] if active_scalar_items else (active_rows[0] if active_rows else None)
    )
    return result


def build_session(
    *queued_results: Mock,
    result: Mock | None = None,
) -> Any:
    session = Mock(spec=AsyncSession)
    default_result = result or build_result()
    result_queue = list(queued_results)

    session.added = []
    session.deleted = []
    session.flush_count = 0
    session.executed_statements = []

    def add(value: Any) -> None:
        session.added.append(value)

    async def delete(value: Any) -> None:
        session.deleted.append(value)

    async def flush() -> None:
        session.flush_count += 1

    async def execute(statement: Any) -> Mock:
        session.executed_statements.append(statement)
        if result_queue:
            return result_queue.pop(0)
        return default_result

    session.add.side_effect = add
    session.delete = AsyncMock(side_effect=delete)
    session.flush = AsyncMock(side_effect=flush)
    session.execute = AsyncMock(side_effect=execute)
    return session


async def test_create_adds_ticket_to_session() -> None:
    session = build_session()
    repository = SqlAlchemyTicketRepository(session)

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
    session = build_session(result=build_result(scalar=ticket))
    repository = SqlAlchemyTicketRepository(session)

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
    session = build_session(result=build_result(scalar=ticket))
    repository = SqlAlchemyTicketRepository(session)

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
    session = build_session(result=build_result(scalar=ticket))
    repository = SqlAlchemyTicketRepository(session)

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
    session = build_session(result=build_result(scalar=ticket))
    repository = SqlAlchemyTicketRepository(session)

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
    session = build_session(result=build_result(scalar=ticket))
    repository = SqlAlchemyTicketRepository(session)

    result = await repository.close(ticket_public_id=ticket.public_id)

    assert cast(object, result) is ticket
    assert ticket.status == TicketStatus.CLOSED
    assert ticket.closed_at is not None
    assert session.flush_count == 1


async def test_count_by_status_returns_mapping() -> None:
    session = build_session(
        result=build_result(
            rows=[
                (TicketStatus.NEW, 2),
                (TicketStatus.CLOSED, 1),
            ]
        )
    )
    repository = SqlAlchemyTicketRepository(session)

    result = await repository.count_by_status()

    assert result == {
        TicketStatus.NEW: 2,
        TicketStatus.CLOSED: 1,
    }


async def test_count_active_tickets_per_operator_returns_grouped_load() -> None:
    session = build_session(
        result=build_result(
            rows=[
                (7, "Operator One", 3),
                (9, "Operator Two", 1),
            ]
        )
    )
    repository = SqlAlchemyTicketRepository(session)

    result = await repository.count_active_tickets_per_operator()

    assert [(item.operator_id, item.display_name, item.ticket_count) for item in result] == [
        (7, "Operator One", 3),
        (9, "Operator Two", 1),
    ]


async def test_get_average_first_response_time_seconds_returns_float() -> None:
    session = build_session(result=build_result(scalar=125.5))
    repository = SqlAlchemyTicketRepository(session)

    result = await repository.get_average_first_response_time_seconds()

    assert result == 125.5


async def test_get_average_resolution_time_seconds_returns_float() -> None:
    session = build_session(result=build_result(scalar=3600))
    repository = SqlAlchemyTicketRepository(session)

    result = await repository.get_average_resolution_time_seconds()

    assert result == 3600.0


async def test_operator_exists_active_by_telegram_user_id_returns_true() -> None:
    session = build_session(result=build_result(scalar=7))
    repository = SqlAlchemyOperatorRepository(session)

    result = await repository.exists_active_by_telegram_user_id(telegram_user_id=1001)

    assert result is True


async def test_operator_exists_active_by_telegram_user_id_returns_false() -> None:
    session = build_session(result=build_result(scalar=None))
    repository = SqlAlchemyOperatorRepository(session)

    result = await repository.exists_active_by_telegram_user_id(telegram_user_id=1001)

    assert result is False


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
    session = build_session(
        build_result(scalar=ticket),
        build_result(scalar="Operator One"),
        build_result(rows=[("Latest client message", TicketMessageSenderType.CLIENT)]),
        build_result(scalar_items=["billing", "vip"]),
    )
    repository = SqlAlchemyTicketRepository(session)

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
    session = build_session(result=build_result(scalar=first_ticket))
    repository = SqlAlchemyTicketRepository(session)

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
    session = build_session(result=build_result(scalar_items=[first_ticket, second_ticket]))
    repository = SqlAlchemyTicketRepository(session)

    result = await repository.list_queued_tickets(limit=2)

    assert [ticket.subject for ticket in result] == ["First", "Second"]


async def test_list_open_tickets_returns_only_non_closed_items() -> None:
    open_ticket = Ticket(
        client_chat_id=100,
        subject="Open",
        priority=TicketPriority.NORMAL,
        public_id=uuid4(),
        status=TicketStatus.ASSIGNED,
    )
    session = build_session(result=build_result(scalar_items=[open_ticket]))
    repository = SqlAlchemyTicketRepository(session)

    result = await repository.list_open_tickets(limit=5)

    assert len(result) == 1
    assert cast(object, result[0]) is open_ticket


async def test_ticket_message_repository_allocates_negative_internal_ids() -> None:
    session = build_session(result=build_result(scalar=-4))
    repository = SqlAlchemyTicketMessageRepository(session)

    result = await repository.allocate_internal_telegram_message_id(
        ticket_id=10,
        sender_type=TicketMessageSenderType.OPERATOR,
    )

    assert result == -5


async def test_ticket_event_repository_persists_event_rows() -> None:
    session = build_session()
    repository = SqlAlchemyTicketEventRepository(session)

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


async def test_ticket_event_repository_exists_checks_for_prior_event() -> None:
    session = build_session(result=build_result(scalar=10))
    repository = SqlAlchemyTicketEventRepository(session)

    result = await repository.exists(
        ticket_id=10,
        event_type=TicketEventType.SLA_BREACHED_FIRST_RESPONSE,
    )

    assert result is True


async def test_sla_policy_repository_prefers_priority_specific_policy() -> None:
    policy = SLAPolicy(
        name="Urgent",
        first_response_minutes=10,
        resolution_minutes=60,
        priority=TicketPriority.URGENT,
    )
    policy.id = 1
    session = build_session(result=build_result(scalar=policy))
    repository = SqlAlchemySLAPolicyRepository(session)

    result = await repository.get_for_priority(priority=TicketPriority.URGENT)

    assert result is policy


async def test_macro_repository_lists_and_fetches_macros() -> None:
    first_macro = Macro(title="First", body="Hello")
    first_macro.id = 1
    second_macro = Macro(title="Second", body="World")
    second_macro.id = 2
    session = build_session(
        build_result(scalar_items=[first_macro, second_macro]),
        build_result(scalar=second_macro),
    )
    repository = SqlAlchemyMacroRepository(session)

    listed = await repository.list_all()
    fetched = await repository.get_by_id(macro_id=2)

    assert [macro.title for macro in listed] == ["First", "Second"]
    assert fetched is second_macro


async def test_tag_repository_normalizes_and_lists_tags() -> None:
    existing_tag = Tag(name="vip")
    existing_tag.id = 3
    session = build_session(
        build_result(scalar=existing_tag),
        build_result(scalar=existing_tag),
        build_result(scalar_items=[existing_tag]),
    )
    repository = SqlAlchemyTagRepository(session)

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
    session = build_session(
        build_result(scalar=None),
        build_result(scalar=existing_link),
        build_result(scalar_items=[first_tag]),
    )
    repository = SqlAlchemyTicketTagRepository(session)

    added = await repository.add(ticket_id=5, tag_id=10)
    removed = await repository.remove(ticket_id=5, tag_id=10)
    listed = await repository.list_for_ticket(ticket_id=5)

    assert added is True
    assert removed is True
    assert listed == [first_tag]
    assert isinstance(session.added[0], TicketTag)
    assert session.deleted == [existing_link]
