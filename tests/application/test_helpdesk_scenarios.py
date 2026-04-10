from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

import pytest

from application.services.authorization import AuthorizationError, AuthorizationService, Permission
from application.services.helpdesk.service import HelpdeskService
from domain.contracts.repositories import (
    MacroRepository,
    OperatorRepository,
    SLAPolicyRepository,
    TagRepository,
    TicketCategoryRepository,
    TicketEventRepository,
    TicketFeedbackRepository,
    TicketInternalNoteRepository,
    TicketMessageRepository,
    TicketRepository,
    TicketTagRepository,
)
from domain.entities.ticket import TicketDetails, TicketInternalNoteDetails, TicketMessageDetails
from domain.enums.roles import UserRole
from domain.enums.tickets import (
    TicketEventType,
    TicketMessageSenderType,
    TicketPriority,
    TicketStatus,
)


@dataclass(slots=True)
class InMemoryTicketRecord:
    id: int
    public_id: UUID
    client_chat_id: int
    status: TicketStatus
    priority: TicketPriority
    subject: str
    category_id: int | None
    assigned_operator_id: int | None
    created_at: datetime
    updated_at: datetime
    first_response_at: datetime | None = None
    closed_at: datetime | None = None
    assigned_operator_name: str | None = None
    assigned_operator_telegram_user_id: int | None = None
    last_message_text: str | None = None
    last_message_sender_type: TicketMessageSenderType | None = None
    message_history: tuple[TicketMessageDetails, ...] = ()
    internal_notes: tuple[TicketInternalNoteDetails, ...] = ()
    tags: tuple[str, ...] = ()
    category_code: str | None = None
    category_title: str | None = None


@dataclass(slots=True)
class InMemoryOperatorRepository:
    active_operator_ids: set[int] = field(default_factory=set)
    display_names: dict[int, str] = field(default_factory=dict)
    usernames: dict[int, str | None] = field(default_factory=dict)
    operator_ids_by_telegram_user_id: dict[int, int] = field(default_factory=dict)
    telegram_user_ids_by_operator_id: dict[int, int] = field(default_factory=dict)
    operator_display_names: dict[int, str] = field(default_factory=dict)
    next_operator_id: int = 1

    def _ensure_operator_id(self, telegram_user_id: int) -> int:
        operator_id = self.operator_ids_by_telegram_user_id.get(telegram_user_id)
        if operator_id is not None:
            return operator_id

        operator_id = self.next_operator_id
        self.next_operator_id += 1
        self.operator_ids_by_telegram_user_id[telegram_user_id] = operator_id
        self.telegram_user_ids_by_operator_id[operator_id] = telegram_user_id
        return operator_id

    async def exists_active_by_telegram_user_id(self, *, telegram_user_id: int) -> bool:
        return telegram_user_id in self.active_operator_ids

    async def list_active(self) -> Sequence[SimpleNamespace]:
        return [
            SimpleNamespace(
                id=self.operator_ids_by_telegram_user_id[telegram_user_id],
                telegram_user_id=telegram_user_id,
                username=self.usernames.get(telegram_user_id),
                display_name=self.display_names[telegram_user_id],
                is_active=True,
            )
            for telegram_user_id in sorted(self.active_operator_ids)
        ]

    async def promote(
        self,
        *,
        telegram_user_id: int,
        display_name: str,
        username: str | None = None,
    ) -> SimpleNamespace:
        operator_id = self._ensure_operator_id(telegram_user_id)
        self.active_operator_ids.add(telegram_user_id)
        self.display_names[telegram_user_id] = display_name
        self.usernames[telegram_user_id] = username
        self.operator_display_names[operator_id] = display_name
        return SimpleNamespace(
            id=operator_id,
            telegram_user_id=telegram_user_id,
            username=username,
            display_name=display_name,
            is_active=True,
        )

    async def revoke(self, *, telegram_user_id: int) -> SimpleNamespace | None:
        if telegram_user_id not in self.active_operator_ids:
            return None

        self.active_operator_ids.remove(telegram_user_id)
        operator_id = self._ensure_operator_id(telegram_user_id)
        return SimpleNamespace(
            id=operator_id,
            telegram_user_id=telegram_user_id,
            username=self.usernames.get(telegram_user_id),
            display_name=self.display_names[telegram_user_id],
            is_active=False,
        )

    async def get_or_create(
        self,
        *,
        telegram_user_id: int,
        display_name: str,
        username: str | None = None,
    ) -> int:
        operator_id = self._ensure_operator_id(telegram_user_id)
        self.active_operator_ids.add(telegram_user_id)
        self.display_names[telegram_user_id] = display_name
        self.usernames[telegram_user_id] = username
        self.operator_display_names[operator_id] = display_name
        return operator_id


@dataclass(slots=True)
class InMemoryTicketRepository:
    operator_display_names: dict[int, str]
    operator_telegram_user_ids: dict[int, int]
    next_ticket_id: int = 1
    tickets: dict[UUID, InMemoryTicketRecord] = field(default_factory=dict)

    async def create(
        self,
        *,
        client_chat_id: int,
        subject: str,
        category_id: int | None = None,
        priority: TicketPriority = TicketPriority.NORMAL,
    ) -> InMemoryTicketRecord:
        now = datetime.now(UTC)
        ticket = InMemoryTicketRecord(
            id=self.next_ticket_id,
            public_id=uuid4(),
            client_chat_id=client_chat_id,
            status=TicketStatus.NEW,
            priority=priority,
            subject=subject,
            category_id=category_id,
            assigned_operator_id=None,
            created_at=now,
            updated_at=now,
        )
        self.next_ticket_id += 1
        self.tickets[ticket.public_id] = ticket
        return ticket

    async def get_by_public_id(self, public_id: UUID) -> InMemoryTicketRecord | None:
        return self.tickets.get(public_id)

    async def get_details_by_public_id(self, public_id: UUID) -> TicketDetails | None:
        ticket = self.tickets.get(public_id)
        if ticket is None:
            return None

        return TicketDetails(
            id=ticket.id,
            public_id=ticket.public_id,
            client_chat_id=ticket.client_chat_id,
            status=ticket.status,
            priority=ticket.priority,
            subject=ticket.subject,
            assigned_operator_id=ticket.assigned_operator_id,
            assigned_operator_name=ticket.assigned_operator_name,
            assigned_operator_telegram_user_id=ticket.assigned_operator_telegram_user_id,
            created_at=ticket.created_at,
            updated_at=ticket.updated_at,
            first_response_at=ticket.first_response_at,
            closed_at=ticket.closed_at,
            category_id=ticket.category_id,
            category_code=ticket.category_code,
            category_title=ticket.category_title,
            tags=ticket.tags,
            last_message_text=ticket.last_message_text,
            last_message_sender_type=ticket.last_message_sender_type,
            message_history=ticket.message_history,
            internal_notes=ticket.internal_notes,
        )

    async def get_active_by_client_chat_id(
        self, client_chat_id: int
    ) -> InMemoryTicketRecord | None:
        active_tickets = [
            ticket
            for ticket in self.tickets.values()
            if ticket.client_chat_id == client_chat_id and ticket.status != TicketStatus.CLOSED
        ]
        if not active_tickets:
            return None
        return max(active_tickets, key=lambda ticket: (ticket.updated_at, ticket.id))

    async def get_next_queued_ticket(
        self, *, prioritize_priority: bool = False
    ) -> InMemoryTicketRecord | None:
        queued_tickets = [
            ticket for ticket in self.tickets.values() if ticket.status == TicketStatus.QUEUED
        ]
        if not queued_tickets:
            return None
        return min(queued_tickets, key=lambda ticket: (ticket.created_at, ticket.id))

    async def list_queued_tickets(
        self,
        *,
        limit: int | None = None,
        prioritize_priority: bool = False,
    ) -> Sequence[InMemoryTicketRecord]:
        queued_tickets = sorted(
            (ticket for ticket in self.tickets.values() if ticket.status == TicketStatus.QUEUED),
            key=lambda ticket: (ticket.created_at, ticket.id),
        )
        if limit is None:
            return queued_tickets
        return queued_tickets[:limit]

    async def list_open_tickets(
        self, *, limit: int | None = None
    ) -> Sequence[InMemoryTicketRecord]:
        open_tickets = sorted(
            (ticket for ticket in self.tickets.values() if ticket.status != TicketStatus.CLOSED),
            key=lambda ticket: (ticket.updated_at, ticket.id),
        )
        if limit is None:
            return open_tickets
        return open_tickets[:limit]

    async def enqueue(self, *, ticket_public_id: UUID) -> InMemoryTicketRecord | None:
        ticket = self.tickets.get(ticket_public_id)
        if ticket is None:
            return None
        ticket.status = TicketStatus.QUEUED
        ticket.updated_at = datetime.now(UTC)
        return ticket

    async def assign_queued_to_operator(
        self,
        *,
        ticket_public_id: UUID,
        operator_id: int,
    ) -> InMemoryTicketRecord | None:
        ticket = self.tickets.get(ticket_public_id)
        if ticket is None or ticket.status != TicketStatus.QUEUED:
            return None

        ticket.status = TicketStatus.ASSIGNED
        ticket.assigned_operator_id = operator_id
        ticket.assigned_operator_name = self.operator_display_names.get(operator_id)
        ticket.assigned_operator_telegram_user_id = self.operator_telegram_user_ids.get(operator_id)
        ticket.updated_at = datetime.now(UTC)
        return ticket

    async def assign_to_operator(
        self,
        *,
        ticket_public_id: UUID,
        operator_id: int,
    ) -> InMemoryTicketRecord | None:
        ticket = self.tickets.get(ticket_public_id)
        if ticket is None:
            return None

        ticket.status = TicketStatus.ASSIGNED
        ticket.assigned_operator_id = operator_id
        ticket.assigned_operator_name = self.operator_display_names.get(operator_id)
        ticket.assigned_operator_telegram_user_id = self.operator_telegram_user_ids.get(operator_id)
        ticket.updated_at = datetime.now(UTC)
        return ticket

    async def escalate(self, *, ticket_public_id: UUID) -> InMemoryTicketRecord | None:
        ticket = self.tickets.get(ticket_public_id)
        if ticket is None:
            return None
        ticket.status = TicketStatus.ESCALATED
        ticket.updated_at = datetime.now(UTC)
        return ticket

    async def close(self, *, ticket_public_id: UUID) -> InMemoryTicketRecord | None:
        ticket = self.tickets.get(ticket_public_id)
        if ticket is None:
            return None
        now = datetime.now(UTC)
        ticket.status = TicketStatus.CLOSED
        ticket.updated_at = now
        ticket.closed_at = now
        return ticket

    async def count_by_status(self) -> Mapping[TicketStatus, int]:
        counts: dict[TicketStatus, int] = {}
        for ticket in self.tickets.values():
            counts[ticket.status] = counts.get(ticket.status, 0) + 1
        return counts

    async def count_active_tickets_per_operator(self) -> Sequence[SimpleNamespace]:
        active_counts: dict[int, int] = {}
        for ticket in self.tickets.values():
            if ticket.assigned_operator_id is None or ticket.status == TicketStatus.CLOSED:
                continue
            active_counts[ticket.assigned_operator_id] = (
                active_counts.get(ticket.assigned_operator_id, 0) + 1
            )

        return [
            SimpleNamespace(
                operator_id=operator_id,
                display_name=self.operator_display_names.get(
                    operator_id, f"Operator {operator_id}"
                ),
                ticket_count=ticket_count,
            )
            for operator_id, ticket_count in sorted(active_counts.items())
        ]

    async def get_average_first_response_time_seconds(self) -> float | None:
        return None

    async def get_average_resolution_time_seconds(self) -> float | None:
        return None

    def set_last_message(
        self,
        *,
        ticket_id: int,
        telegram_message_id: int,
        text: str | None,
        sender_type: TicketMessageSenderType,
        sender_operator_id: int | None = None,
        sender_operator_name: str | None = None,
        created_at: datetime | None = None,
    ) -> None:
        for ticket in self.tickets.values():
            if ticket.id == ticket_id:
                ticket.last_message_text = text
                ticket.last_message_sender_type = sender_type
                ticket.message_history = (
                    *ticket.message_history,
                    TicketMessageDetails(
                        telegram_message_id=telegram_message_id,
                        sender_type=sender_type,
                        sender_operator_id=sender_operator_id,
                        sender_operator_name=sender_operator_name,
                        text=text,
                        created_at=created_at or datetime.now(UTC),
                    ),
                )
                return


@dataclass(slots=True)
class InMemoryMessageRepository:
    ticket_repository: InMemoryTicketRepository
    added_messages: list[dict[str, object]] = field(default_factory=list)

    async def add(
        self,
        *,
        ticket_id: int,
        telegram_message_id: int,
        sender_type: TicketMessageSenderType,
        text: str | None,
        attachment: object | None = None,
        sender_operator_id: int | None = None,
    ) -> None:
        self.added_messages.append(
            {
                "ticket_id": ticket_id,
                "telegram_message_id": telegram_message_id,
                "sender_type": sender_type,
                "text": text,
                "attachment": attachment,
                "sender_operator_id": sender_operator_id,
            }
        )
        self.ticket_repository.set_last_message(
            ticket_id=ticket_id,
            telegram_message_id=telegram_message_id,
            text=text,
            sender_type=sender_type,
            sender_operator_id=sender_operator_id,
            sender_operator_name=self.ticket_repository.operator_display_names.get(
                sender_operator_id
            )
            if sender_operator_id is not None
            else None,
            created_at=datetime.now(UTC),
        )

    async def allocate_internal_telegram_message_id(
        self,
        *,
        ticket_id: int,
        sender_type: TicketMessageSenderType,
    ) -> int:
        return -ticket_id


@dataclass(slots=True)
class InMemoryInternalNoteRepository:
    ticket_repository: InMemoryTicketRepository
    added_notes: list[dict[str, object]] = field(default_factory=list)

    async def add(
        self,
        *,
        ticket_id: int,
        author_operator_id: int,
        text: str,
    ) -> TicketInternalNoteDetails:
        note = TicketInternalNoteDetails(
            id=len(self.added_notes) + 1,
            author_operator_id=author_operator_id,
            author_operator_name=self.ticket_repository.operator_display_names.get(
                author_operator_id
            ),
            text=text,
            created_at=datetime.now(UTC),
        )
        self.added_notes.append(
            {
                "ticket_id": ticket_id,
                "author_operator_id": author_operator_id,
                "text": text,
            }
        )
        for ticket in self.ticket_repository.tickets.values():
            if ticket.id == ticket_id:
                ticket.internal_notes = (*ticket.internal_notes, note)
                ticket.updated_at = note.created_at
                break
        return note


@dataclass(slots=True)
class InMemoryEventRepository:
    added_events: list[dict[str, object]] = field(default_factory=list)

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


class EmptyMacroRepository:
    async def list_all(self) -> Sequence[SimpleNamespace]:
        return []

    async def get_by_id(self, *, macro_id: int) -> SimpleNamespace | None:
        return None

    async def get_by_title(self, *, title: str) -> SimpleNamespace | None:
        return None

    async def create(self, *, title: str, body: str) -> SimpleNamespace:
        return SimpleNamespace(id=1, title=title, body=body)

    async def update_title(self, *, macro_id: int, title: str) -> SimpleNamespace | None:
        return None

    async def update_body(self, *, macro_id: int, body: str) -> SimpleNamespace | None:
        return None

    async def delete(self, *, macro_id: int) -> SimpleNamespace | None:
        return None


class StaticSLAPolicyRepository:
    async def get_for_priority(self, *, priority: TicketPriority) -> SimpleNamespace:
        return SimpleNamespace(
            id=1,
            name="Default",
            first_response_minutes=30,
            resolution_minutes=240,
            priority=None,
        )


class EmptyTagRepository:
    async def get_or_create(self, *, name: str) -> int:
        return 1

    async def get_by_name(self, *, name: str) -> SimpleNamespace | None:
        return None

    async def list_all(self) -> Sequence[SimpleNamespace]:
        return []


class EmptyTicketCategoryRepository:
    async def list_all(self, *, include_inactive: bool = True) -> Sequence[SimpleNamespace]:
        return []

    async def get_by_id(self, *, category_id: int) -> SimpleNamespace | None:
        return None

    async def get_by_code(self, *, code: str) -> SimpleNamespace | None:
        return None

    async def create(
        self,
        *,
        code: str,
        title: str,
        sort_order: int,
        is_active: bool = True,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            id=1,
            code=code,
            title=title,
            sort_order=sort_order,
            is_active=is_active,
        )

    async def update_title(self, *, category_id: int, title: str) -> SimpleNamespace | None:
        return None

    async def set_active(
        self,
        *,
        category_id: int,
        is_active: bool,
    ) -> SimpleNamespace | None:
        return None

    async def get_next_sort_order(self) -> int:
        return 10


class EmptyTicketFeedbackRepository:
    async def get_by_ticket_id(self, *, ticket_id: int) -> SimpleNamespace | None:
        return None

    async def create(
        self,
        *,
        ticket_id: int,
        client_chat_id: int,
        rating: int,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            id=1,
            ticket_id=ticket_id,
            client_chat_id=client_chat_id,
            rating=rating,
            comment=None,
            submitted_at=datetime.now(UTC),
        )

    async def update_comment(self, *, ticket_id: int, comment: str) -> SimpleNamespace | None:
        return None


class EmptyTicketTagRepository:
    async def list_for_ticket(self, *, ticket_id: int) -> Sequence[SimpleNamespace]:
        return []

    async def add(self, *, ticket_id: int, tag_id: int) -> bool:
        return False

    async def remove(self, *, ticket_id: int, tag_id: int) -> bool:
        return False


@dataclass(slots=True)
class HelpdeskScenario:
    helpdesk_service: HelpdeskService
    authorization_service: AuthorizationService
    ticket_repository: InMemoryTicketRepository
    message_repository: InMemoryMessageRepository
    event_repository: InMemoryEventRepository
    operator_repository: InMemoryOperatorRepository
    super_admin_telegram_user_id: int = 42


@pytest.fixture
def helpdesk_scenario() -> HelpdeskScenario:
    operator_repository = InMemoryOperatorRepository()
    ticket_repository = InMemoryTicketRepository(
        operator_display_names=operator_repository.operator_display_names,
        operator_telegram_user_ids=operator_repository.telegram_user_ids_by_operator_id,
    )
    message_repository = InMemoryMessageRepository(ticket_repository=ticket_repository)
    internal_note_repository = InMemoryInternalNoteRepository(
        ticket_repository=ticket_repository
    )
    event_repository = InMemoryEventRepository()
    super_admin_telegram_user_id = 42

    return HelpdeskScenario(
        helpdesk_service=HelpdeskService(
            ticket_repository=cast(TicketRepository, ticket_repository),
            ticket_feedback_repository=cast(
                TicketFeedbackRepository, EmptyTicketFeedbackRepository()
            ),
            ticket_message_repository=cast(TicketMessageRepository, message_repository),
            ticket_internal_note_repository=cast(
                TicketInternalNoteRepository, internal_note_repository
            ),
            ticket_event_repository=cast(TicketEventRepository, event_repository),
            operator_repository=cast(OperatorRepository, operator_repository),
            macro_repository=cast(MacroRepository, EmptyMacroRepository()),
            sla_policy_repository=cast(SLAPolicyRepository, StaticSLAPolicyRepository()),
            tag_repository=cast(TagRepository, EmptyTagRepository()),
            ticket_category_repository=cast(
                TicketCategoryRepository, EmptyTicketCategoryRepository()
            ),
            ticket_tag_repository=cast(TicketTagRepository, EmptyTicketTagRepository()),
            super_admin_telegram_user_ids=frozenset({super_admin_telegram_user_id}),
        ),
        authorization_service=AuthorizationService(
            operator_repository=cast(OperatorRepository, operator_repository),
            super_admin_telegram_user_ids=frozenset({super_admin_telegram_user_id}),
        ),
        ticket_repository=ticket_repository,
        message_repository=message_repository,
        event_repository=event_repository,
        operator_repository=operator_repository,
        super_admin_telegram_user_id=super_admin_telegram_user_id,
    )


async def test_helpdesk_role_and_ticket_flow_scenario(
    helpdesk_scenario: HelpdeskScenario,
) -> None:
    service = helpdesk_scenario.helpdesk_service
    authorization_service = helpdesk_scenario.authorization_service
    super_admin_telegram_user_id = helpdesk_scenario.super_admin_telegram_user_id
    operator_telegram_user_id = 1001
    client_chat_id = 5001

    promotion = await service.promote_operator(
        telegram_user_id=operator_telegram_user_id,
        display_name="Operator One",
        username="operator_one",
        actor_telegram_user_id=super_admin_telegram_user_id,
    )

    assert promotion.changed is True
    assert (
        await authorization_service.resolve_role(telegram_user_id=operator_telegram_user_id)
        == UserRole.OPERATOR
    )

    created_ticket = await service.create_ticket_from_client_message(
        client_chat_id=client_chat_id,
        telegram_message_id=7001,
        text="Не могу войти в личный кабинет",
    )

    assert created_ticket.created is True
    assert created_ticket.status == TicketStatus.QUEUED

    queued_tickets = await service.list_queued_tickets(
        actor_telegram_user_id=operator_telegram_user_id
    )

    assert [ticket.public_id for ticket in queued_tickets] == [created_ticket.public_id]
    assert queued_tickets[0].status == TicketStatus.QUEUED

    taken_ticket = await service.assign_next_ticket_to_operator(
        telegram_user_id=operator_telegram_user_id,
        display_name="Operator One",
        username="operator_one",
        actor_telegram_user_id=operator_telegram_user_id,
    )

    assert taken_ticket is not None
    assert taken_ticket.public_id == created_ticket.public_id
    assert taken_ticket.status == TicketStatus.ASSIGNED

    ticket_details = await service.get_ticket_details(
        ticket_public_id=created_ticket.public_id,
        actor_telegram_user_id=operator_telegram_user_id,
    )

    assert ticket_details is not None
    assert ticket_details.assigned_operator_name == "Operator One"
    assert ticket_details.assigned_operator_telegram_user_id == operator_telegram_user_id
    assert ticket_details.last_message_sender_type == TicketMessageSenderType.CLIENT
    assert ticket_details.message_history[0].text == "Не могу войти в личный кабинет"

    operator_reply = await service.reply_to_ticket_as_operator(
        ticket_public_id=created_ticket.public_id,
        telegram_user_id=operator_telegram_user_id,
        display_name="Operator One",
        username="operator_one",
        telegram_message_id=7002,
        text="Уже проверяем доступ, вернемся с ответом.",
        actor_telegram_user_id=operator_telegram_user_id,
    )

    assert operator_reply is not None
    assert operator_reply.client_chat_id == client_chat_id

    updated_details = await service.get_ticket_details(
        ticket_public_id=created_ticket.public_id,
        actor_telegram_user_id=operator_telegram_user_id,
    )

    assert updated_details is not None
    assert updated_details.last_message_text == "Уже проверяем доступ, вернемся с ответом."
    assert updated_details.last_message_sender_type == TicketMessageSenderType.OPERATOR
    assert [item.text for item in updated_details.message_history] == [
        "Не могу войти в личный кабинет",
        "Уже проверяем доступ, вернемся с ответом.",
    ]
    created_ticket_record = helpdesk_scenario.ticket_repository.tickets[created_ticket.public_id]
    assert created_ticket_record.first_response_at is not None

    operators = await service.list_operators(actor_telegram_user_id=super_admin_telegram_user_id)

    assert [(operator.telegram_user_id, operator.display_name) for operator in operators] == [
        (operator_telegram_user_id, "Operator One"),
    ]

    revocation = await service.revoke_operator(
        telegram_user_id=operator_telegram_user_id,
        actor_telegram_user_id=super_admin_telegram_user_id,
    )

    assert revocation is not None
    assert revocation.operator.is_active is False
    assert (
        await authorization_service.has_permission(
            telegram_user_id=operator_telegram_user_id,
            permission=Permission.ACCESS_OPERATOR,
        )
        is False
    )
    assert (
        await authorization_service.resolve_role(telegram_user_id=operator_telegram_user_id)
        == UserRole.USER
    )

    with pytest.raises(AuthorizationError):
        await service.list_queued_tickets(actor_telegram_user_id=operator_telegram_user_id)

    assert [
        message["sender_type"] for message in helpdesk_scenario.message_repository.added_messages
    ] == [
        TicketMessageSenderType.CLIENT,
        TicketMessageSenderType.OPERATOR,
    ]
    assert [event["event_type"] for event in helpdesk_scenario.event_repository.added_events] == [
        TicketEventType.CREATED,
        TicketEventType.QUEUED,
        TicketEventType.CLIENT_MESSAGE_ADDED,
        TicketEventType.ASSIGNED,
        TicketEventType.OPERATOR_MESSAGE_ADDED,
    ]
