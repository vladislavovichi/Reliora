from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from domain.enums.tickets import TicketPriority, TicketStatus
from infrastructure.db.models import Ticket
from infrastructure.db.repositories import SqlAlchemyTicketRepository


@dataclass
class FakeResult:
    scalar: Any = None
    rows: list[tuple[Any, Any]] = field(default_factory=list)

    def scalar_one_or_none(self) -> Any:
        return self.scalar

    def all(self) -> list[tuple[Any, Any]]:
        return self.rows


@dataclass
class FakeAsyncSession:
    result: FakeResult = field(default_factory=FakeResult)
    added: list[Any] = field(default_factory=list)
    flush_count: int = 0
    executed_statements: list[Any] = field(default_factory=list)

    def add(self, value: Any) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        self.flush_count += 1

    async def execute(self, statement: Any) -> FakeResult:
        self.executed_statements.append(statement)
        return self.result


async def test_create_adds_ticket_to_session() -> None:
    session = FakeAsyncSession()
    repository = SqlAlchemyTicketRepository(cast(AsyncSession, session))

    ticket = await repository.create(
        client_chat_id=100,
        subject="Need access",
        priority=TicketPriority.NORMAL,
    )

    assert session.added == [ticket]
    assert session.flush_count == 1
    assert ticket.client_chat_id == 100
    assert ticket.subject == "Need access"
    assert ticket.status == TicketStatus.NEW


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
