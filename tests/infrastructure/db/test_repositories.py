from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
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
from infrastructure.db.models.catalog import Macro, SLAPolicy, Tag, TicketCategory
from infrastructure.db.models.feedback import TicketFeedback
from infrastructure.db.models.operator import Operator
from infrastructure.db.models.ticket import Ticket, TicketEvent, TicketTag
from infrastructure.db.repositories.catalog import (
    SqlAlchemyMacroRepository,
    SqlAlchemySLAPolicyRepository,
    SqlAlchemyTagRepository,
    SqlAlchemyTicketCategoryRepository,
    SqlAlchemyTicketTagRepository,
)
from infrastructure.db.repositories.feedback import SqlAlchemyTicketFeedbackRepository
from infrastructure.db.repositories.operator_invites import SqlAlchemyOperatorInviteCodeRepository
from infrastructure.db.repositories.operators import SqlAlchemyOperatorRepository
from infrastructure.db.repositories.tickets import (
    SqlAlchemyTicketEventRepository,
    SqlAlchemyTicketMessageRepository,
    SqlAlchemyTicketRepository,
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
        category_id=7,
        priority=TicketPriority.NORMAL,
    )

    assert session.added == [cast(object, ticket)]
    assert session.flush_count == 1
    assert ticket.client_chat_id == 100
    assert ticket.subject == "Need access"
    assert ticket.category_id == 7
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


async def test_create_ticket_feedback_adds_feedback_to_session() -> None:
    session = build_session()
    repository = SqlAlchemyTicketFeedbackRepository(session)

    feedback = await repository.create(ticket_id=7, client_chat_id=1001, rating=5)

    assert session.added == [cast(object, feedback)]
    assert session.flush_count == 1
    assert feedback.ticket_id == 7
    assert feedback.client_chat_id == 1001
    assert feedback.rating == 5


async def test_get_ticket_feedback_by_ticket_id_returns_record() -> None:
    feedback = TicketFeedback(
        ticket_id=7,
        client_chat_id=1001,
        rating=4,
    )
    session = build_session(result=build_result(scalar=feedback))
    repository = SqlAlchemyTicketFeedbackRepository(session)

    result = await repository.get_by_ticket_id(ticket_id=7)

    assert cast(object, result) is feedback


async def test_update_ticket_feedback_comment_persists_comment() -> None:
    feedback = TicketFeedback(
        ticket_id=7,
        client_chat_id=1001,
        rating=4,
    )
    session = build_session(result=build_result(scalar=feedback))
    repository = SqlAlchemyTicketFeedbackRepository(session)

    result = await repository.update_comment(ticket_id=7, comment="Спасибо")

    assert cast(object, result) is feedback
    assert feedback.comment == "Спасибо"
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


async def test_count_created_tickets_returns_integer() -> None:
    session = build_session(result=build_result(scalar=8))
    repository = SqlAlchemyTicketRepository(session)

    result = await repository.count_created_tickets()

    assert result == 8


async def test_count_feedback_submissions_returns_integer() -> None:
    session = build_session(result=build_result(scalar=3))
    repository = SqlAlchemyTicketRepository(session)

    result = await repository.count_feedback_submissions()

    assert result == 3


async def test_get_feedback_rating_distribution_returns_ordered_rows() -> None:
    session = build_session(
        result=build_result(
            rows=[
                (5, 4),
                (4, 2),
            ]
        )
    )
    repository = SqlAlchemyTicketRepository(session)

    result = await repository.get_feedback_rating_distribution()

    assert [(item.rating, item.count) for item in result] == [(5, 4), (4, 2)]


async def test_list_closed_ticket_stats_by_operator_returns_aggregates() -> None:
    session = build_session(
        result=build_result(
            rows=[
                (7, "Operator One", 4, 120.0, 5400.0, 4.8, 3),
            ]
        )
    )
    repository = SqlAlchemyTicketRepository(session)

    result = await repository.list_closed_ticket_stats_by_operator()

    assert result[0].operator_id == 7
    assert result[0].closed_ticket_count == 4
    assert result[0].average_satisfaction == 4.8


async def test_count_sla_breaches_returns_mapping_by_event_type() -> None:
    session = build_session(
        result=build_result(
            rows=[
                (TicketEventType.SLA_BREACHED_FIRST_RESPONSE, 2),
                (TicketEventType.SLA_BREACHED_RESOLUTION, 1),
            ]
        )
    )
    repository = SqlAlchemyTicketRepository(session)

    result = await repository.count_sla_breaches()

    assert result == {
        "sla_breached_first_response": 2,
        "sla_breached_resolution": 1,
    }


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


async def test_list_active_operators_returns_sequence() -> None:
    first_operator = Operator(
        telegram_user_id=1001,
        username="anna",
        display_name="Анна",
        is_active=True,
    )
    second_operator = Operator(
        telegram_user_id=1002,
        username=None,
        display_name="Борис",
        is_active=True,
    )
    session = build_session(result=build_result(scalar_items=[first_operator, second_operator]))
    repository = SqlAlchemyOperatorRepository(session)

    result = await repository.list_active()

    assert [operator.telegram_user_id for operator in result] == [1001, 1002]


async def test_promote_operator_creates_new_record() -> None:
    session = build_session(build_result(scalar=None))
    repository = SqlAlchemyOperatorRepository(session)

    operator = await repository.promote(
        telegram_user_id=2001,
        display_name="Оператор 2001",
        username=None,
    )

    assert operator.telegram_user_id == 2001
    assert operator.display_name == "Оператор 2001"
    assert operator.is_active is True
    assert session.flush_count == 1


async def test_revoke_operator_marks_record_inactive() -> None:
    operator = Operator(
        telegram_user_id=2001,
        username="user2001",
        display_name="Оператор 2001",
        is_active=True,
    )
    session = build_session(result=build_result(scalar=operator))
    repository = SqlAlchemyOperatorRepository(session)

    result = await repository.revoke(telegram_user_id=2001)

    assert result is operator
    assert operator.is_active is False
    assert session.flush_count == 1


async def test_create_operator_invite_code_persists_record() -> None:
    session = build_session()
    repository = SqlAlchemyOperatorInviteCodeRepository(session)

    invite = await repository.create(
        code_hash="hash-1",
        created_by_telegram_user_id=42,
        expires_at=datetime(2026, 4, 15, 12, 0, tzinfo=UTC),
    )

    assert invite.code_hash == "hash-1"
    assert invite.max_uses == 1
    assert invite.is_active is True
    assert session.flush_count == 1


async def test_mark_used_operator_invite_code_deactivates_when_limit_reached() -> None:
    invite = SimpleNamespace(
        id=1,
        code_hash="hash-1",
        created_by_telegram_user_id=42,
        expires_at=datetime(2026, 4, 15, 12, 0, tzinfo=UTC),
        max_uses=1,
        used_count=0,
        is_active=True,
        last_used_at=None,
        last_used_telegram_user_id=None,
        deactivated_at=None,
    )
    session = build_session(result=build_result(scalar=invite))
    repository = SqlAlchemyOperatorInviteCodeRepository(session)

    result = await repository.mark_used(
        invite_id=1,
        telegram_user_id=3001,
        used_at=datetime(2026, 4, 12, 12, 0, tzinfo=UTC),
    )

    assert result is not None
    assert invite.used_count == 1
    assert invite.is_active is False
    assert invite.last_used_telegram_user_id == 3001


async def test_get_details_by_public_id_returns_enriched_ticket_view_with_tags() -> None:
    ticket = Ticket(
        client_chat_id=100,
        subject="Need access",
        priority=TicketPriority.NORMAL,
        public_id=uuid4(),
        status=TicketStatus.ASSIGNED,
        assigned_operator_id=77,
        category_id=9,
    )
    ticket.id = 1
    session = build_session(
        build_result(scalar=ticket),
        build_result(rows=[("Operator One", 1001, "operator_one")]),
        build_result(rows=[("access", "Доступ и вход")]),
        build_result(rows=[("Latest client message", TicketMessageSenderType.CLIENT)]),
        build_result(scalar_items=["billing", "vip"]),
        build_result(
            rows=[
                (
                    11,
                    TicketMessageSenderType.CLIENT,
                    None,
                    None,
                    "First client message",
                    datetime(2026, 4, 7, 9, 0, tzinfo=UTC),
                ),
                (
                    12,
                    TicketMessageSenderType.OPERATOR,
                    77,
                    "Operator One",
                    "Operator answer",
                    datetime(2026, 4, 7, 9, 5, tzinfo=UTC),
                ),
            ]
        ),
    )
    repository = SqlAlchemyTicketRepository(session)

    result = await repository.get_details_by_public_id(ticket.public_id)

    assert result is not None
    assert result.public_id == ticket.public_id
    assert result.assigned_operator_name == "Operator One"
    assert result.assigned_operator_telegram_user_id == 1001
    assert result.category_code == "access"
    assert result.category_title == "Доступ и вход"
    assert result.last_message_text == "Latest client message"
    assert result.tags == ("billing", "vip")
    assert [message.text for message in result.message_history] == [
        "First client message",
        "Operator answer",
    ]


async def test_list_ticket_events_returns_ordered_event_details() -> None:
    session = build_session(
        result=build_result(
            rows=[
                (
                    TicketEventType.CREATED,
                    {"status": "new"},
                    datetime(2026, 4, 7, 9, 0, tzinfo=UTC),
                ),
                (
                    TicketEventType.CLOSED,
                    {"from_status": "assigned", "to_status": "closed"},
                    datetime(2026, 4, 7, 10, 0, tzinfo=UTC),
                ),
            ]
        )
    )
    repository = SqlAlchemyTicketEventRepository(session)

    result = await repository.list_for_ticket(ticket_id=7)

    assert [event.event_type for event in result] == [
        TicketEventType.CREATED,
        TicketEventType.CLOSED,
    ]
    assert result[1].payload_json == {"from_status": "assigned", "to_status": "closed"}


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


async def test_macro_repository_creates_updates_and_deletes_macros() -> None:
    existing_macro = Macro(title="Old", body="Body")
    existing_macro.id = 7
    session = build_session(
        build_result(scalar=existing_macro),
        build_result(scalar=existing_macro),
        build_result(scalar=existing_macro),
    )
    repository = SqlAlchemyMacroRepository(session)

    created = await repository.create(title="New", body="Created body")
    updated_title = await repository.update_title(macro_id=7, title="Renamed")
    updated_body = await repository.update_body(macro_id=7, body="Updated body")
    deleted = await repository.delete(macro_id=7)

    assert isinstance(session.added[0], Macro)
    assert created.title == "New"
    assert created.body == "Created body"
    assert updated_title is existing_macro
    assert existing_macro.title == "Renamed"
    assert updated_body is existing_macro
    assert existing_macro.body == "Updated body"
    assert deleted is existing_macro
    assert session.deleted == [existing_macro]


async def test_ticket_category_repository_lists_creates_and_updates_categories() -> None:
    existing_category = TicketCategory(
        code="access",
        title="Доступ и вход",
        is_active=True,
        sort_order=10,
    )
    existing_category.id = 1
    session = build_session(
        build_result(scalar_items=[existing_category]),
        build_result(scalar=existing_category),
        build_result(scalar=existing_category),
        build_result(scalar=20),
    )
    repository = SqlAlchemyTicketCategoryRepository(session)

    listed = await repository.list_all(include_inactive=False)
    updated_title = await repository.update_title(category_id=1, title="Доступ")
    updated_active = await repository.set_active(category_id=1, is_active=False)
    next_sort_order = await repository.get_next_sort_order()

    created = await repository.create(
        code="other",
        title="Другая тема",
        sort_order=30,
    )

    assert listed == [existing_category]
    assert updated_title is existing_category
    assert existing_category.title == "Доступ"
    assert updated_active is existing_category
    assert existing_category.is_active is False
    assert next_sort_order == 30
    assert isinstance(session.added[0], TicketCategory)
    assert created.code == "other"


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
