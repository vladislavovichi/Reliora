from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from uuid import UUID, uuid4

from application.services.helpdesk import HelpdeskService
from domain.enums.tickets import TicketMessageSenderType, TicketStatus


@dataclass
class StubTicketRepository:
    created_ticket: SimpleNamespace
    assigned_ticket: SimpleNamespace | None = None
    closed_ticket: SimpleNamespace | None = None
    by_status: dict[TicketStatus, int] | None = None

    def __post_init__(self) -> None:
        self.create_calls: list[dict[str, object]] = []
        self.get_calls: list[UUID] = []
        self.assign_calls: list[dict[str, object]] = []
        self.close_calls: list[UUID] = []

    async def create(self, *, client_chat_id: int, subject: str, priority: object = None) -> SimpleNamespace:
        self.create_calls.append(
            {
                "client_chat_id": client_chat_id,
                "subject": subject,
                "priority": priority,
            }
        )
        return self.created_ticket

    async def get_by_public_id(self, public_id: UUID) -> SimpleNamespace | None:
        self.get_calls.append(public_id)
        if self.assigned_ticket is not None and self.assigned_ticket.public_id == public_id:
            return self.assigned_ticket
        if self.closed_ticket is not None and self.closed_ticket.public_id == public_id:
            return self.closed_ticket
        if self.created_ticket.public_id == public_id:
            return self.created_ticket
        return None

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
        return self.assigned_ticket

    async def close(self, *, ticket_public_id: UUID) -> SimpleNamespace | None:
        self.close_calls.append(ticket_public_id)
        return self.closed_ticket

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
class StubOperatorRepository:
    operator_id: int

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
        return self.operator_id


@dataclass
class StubTagRepository:
    async def get_or_create(self, *, name: str) -> int:
        return 1


def build_ticket(*, ticket_id: int, public_id: UUID, status: TicketStatus) -> SimpleNamespace:
    return SimpleNamespace(
        id=ticket_id,
        public_id=public_id,
        client_chat_id=123,
        status=status,
        priority="normal",
        subject="Need help",
        assigned_operator_id=None,
        created_at=None,
        updated_at=None,
        first_response_at=None,
        closed_at=None,
    )


async def test_create_ticket_from_client_message_returns_ticket_summary() -> None:
    public_id = uuid4()
    ticket_repository = StubTicketRepository(
        created_ticket=build_ticket(ticket_id=1, public_id=public_id, status=TicketStatus.NEW)
    )
    message_repository = StubTicketMessageRepository(added_messages=[])
    service = HelpdeskService(
        ticket_repository=ticket_repository,
        ticket_message_repository=message_repository,
        operator_repository=StubOperatorRepository(operator_id=10),
        tag_repository=StubTagRepository(),
    )

    result = await service.create_ticket_from_client_message(
        client_chat_id=555,
        telegram_message_id=777,
        text="Cannot log in",
    )

    assert result.public_id == public_id
    assert result.public_number.startswith("HD-")
    assert result.status == TicketStatus.NEW
    assert message_repository.added_messages[0]["sender_type"] == TicketMessageSenderType.CLIENT


async def test_assign_ticket_to_operator_uses_operator_repository() -> None:
    public_id = uuid4()
    assigned_ticket = build_ticket(ticket_id=1, public_id=public_id, status=TicketStatus.ASSIGNED)
    ticket_repository = StubTicketRepository(
        created_ticket=assigned_ticket,
        assigned_ticket=assigned_ticket,
    )
    operator_repository = StubOperatorRepository(operator_id=42)
    service = HelpdeskService(
        ticket_repository=ticket_repository,
        ticket_message_repository=StubTicketMessageRepository(added_messages=[]),
        operator_repository=operator_repository,
        tag_repository=StubTagRepository(),
    )

    result = await service.assign_ticket_to_operator(
        ticket_public_id=public_id,
        telegram_user_id=999,
        display_name="Operator",
        username="operator_1",
    )

    assert result is not None
    assert result.status == TicketStatus.ASSIGNED
    assert operator_repository.calls[0]["telegram_user_id"] == 999
    assert ticket_repository.assign_calls[0]["operator_id"] == 42


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
        operator_repository=StubOperatorRepository(operator_id=1),
        tag_repository=StubTagRepository(),
    )

    stats = await service.get_basic_stats()

    assert stats.total == 6
    assert stats.open_total == 5
    assert stats.by_status[TicketStatus.CLOSED] == 1
