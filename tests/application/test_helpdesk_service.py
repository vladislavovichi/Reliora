from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

from application.services.authorization import AuthorizationError
from application.services.helpdesk.service import HelpdeskService
from application.use_cases.tickets.exports import TicketReportFormat
from application.use_cases.tickets.summaries import (
    CategoryManagementError,
    MacroManagementError,
    OperatorManagementError,
    SLAAutoReassignmentTarget,
    TagSummary,
)
from domain.entities.ticket import TicketDetails, TicketMessageDetails
from domain.enums.tickets import (
    TicketEventType,
    TicketMessageSenderType,
    TicketPriority,
    TicketStatus,
)
from domain.tickets import InvalidTicketTransitionError


def normalize_tag_name(name: str) -> str:
    return " ".join(name.strip().lower().split())


@dataclass
class StubTicketRepository:
    created_ticket: SimpleNamespace
    active_ticket: SimpleNamespace | None = None
    queued_tickets: list[SimpleNamespace] | None = None
    by_status: dict[TicketStatus, int] | None = None
    active_operator_ticket_loads: list[SimpleNamespace] | None = None
    average_first_response_time_seconds: float | None = None
    average_resolution_time_seconds: float | None = None

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
        self.count_active_tickets_per_operator_calls = 0
        self.average_first_response_calls = 0
        self.average_resolution_calls = 0
        self.tickets: dict[UUID, SimpleNamespace] = {
            self.created_ticket.public_id: self.created_ticket,
        }
        if self.active_ticket is not None:
            self.tickets[self.active_ticket.public_id] = self.active_ticket
        if self.queued_tickets is None:
            self.queued_tickets = []
        if self.active_operator_ticket_loads is None:
            self.active_operator_ticket_loads = []
        for ticket in self.queued_tickets:
            self.tickets[ticket.public_id] = ticket

    async def create(
        self,
        *,
        client_chat_id: int,
        subject: str,
        category_id: int | None = None,
        priority: object = None,
    ) -> SimpleNamespace:
        self.create_calls.append(
            {
                "client_chat_id": client_chat_id,
                "subject": subject,
                "category_id": category_id,
                "priority": priority,
            }
        )
        self.created_ticket.category_id = category_id
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
            assigned_operator_telegram_user_id=getattr(
                ticket, "assigned_operator_telegram_user_id", None
            ),
            created_at=ticket.created_at,
            updated_at=ticket.updated_at,
            first_response_at=ticket.first_response_at,
            closed_at=ticket.closed_at,
            category_id=getattr(ticket, "category_id", None),
            category_code=getattr(ticket, "category_code", None),
            category_title=getattr(ticket, "category_title", None),
            tags=tuple(getattr(ticket, "tags", ())),
            last_message_text=getattr(ticket, "last_message_text", None),
            last_message_sender_type=getattr(ticket, "last_message_sender_type", None),
            message_history=tuple(getattr(ticket, "message_history", ())),
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
            ticket for ticket in self.queued_tickets or [] if ticket.status == TicketStatus.QUEUED
        ]
        if limit is None:
            return tickets
        return tickets[:limit]

    async def list_open_tickets(self, *, limit: int | None = None) -> list[SimpleNamespace]:
        tickets = [
            ticket for ticket in self.tickets.values() if ticket.status != TicketStatus.CLOSED
        ]
        tickets.sort(key=lambda ticket: (ticket.updated_at, ticket.id))
        if limit is None:
            return tickets
        return tickets[:limit]

    async def list_open_tickets_for_operator(
        self,
        *,
        operator_telegram_user_id: int,
        limit: int | None = None,
    ) -> list[SimpleNamespace]:
        tickets = [
            ticket
            for ticket in self.tickets.values()
            if ticket.status != TicketStatus.CLOSED
            and getattr(ticket, "assigned_operator_telegram_user_id", None)
            == operator_telegram_user_id
        ]
        tickets.sort(key=lambda ticket: (ticket.updated_at, ticket.id), reverse=True)
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

    async def count_active_tickets_per_operator(self) -> list[SimpleNamespace]:
        self.count_active_tickets_per_operator_calls += 1
        return list(self.active_operator_ticket_loads or [])

    async def get_average_first_response_time_seconds(self) -> float | None:
        self.average_first_response_calls += 1
        return self.average_first_response_time_seconds

    async def get_average_resolution_time_seconds(self) -> float | None:
        self.average_resolution_calls += 1
        return self.average_resolution_time_seconds


def build_message_repository_mock(*, next_internal_message_id: int = -1) -> Mock:
    repository = Mock()
    repository.added_messages = []
    repository.allocated_internal_ids = []

    async def add(
        *,
        ticket_id: int,
        telegram_message_id: int,
        sender_type: TicketMessageSenderType,
        text: str,
        sender_operator_id: int | None = None,
    ) -> None:
        repository.added_messages.append(
            {
                "ticket_id": ticket_id,
                "telegram_message_id": telegram_message_id,
                "sender_type": sender_type,
                "text": text,
                "sender_operator_id": sender_operator_id,
            }
        )

    async def allocate_internal_telegram_message_id(
        *,
        ticket_id: int,
        sender_type: TicketMessageSenderType,
    ) -> int:
        repository.allocated_internal_ids.append(
            {
                "ticket_id": ticket_id,
                "sender_type": sender_type,
            }
        )
        return next_internal_message_id

    repository.add = AsyncMock(side_effect=add)
    repository.allocate_internal_telegram_message_id = AsyncMock(
        side_effect=allocate_internal_telegram_message_id
    )
    return repository


def build_event_repository_mock(initial_events: list[SimpleNamespace] | None = None) -> Mock:
    repository = Mock()
    repository.added_events = []
    repository.listed_events = [] if initial_events is None else list(initial_events)

    async def add(
        *,
        ticket_id: int,
        event_type: TicketEventType,
        payload_json: Mapping[str, object] | None = None,
    ) -> None:
        repository.added_events.append(
            {
                "ticket_id": ticket_id,
                "event_type": event_type,
                "payload_json": dict(payload_json) if payload_json is not None else None,
            }
        )

    async def exists(*, ticket_id: int, event_type: TicketEventType) -> bool:
        return any(
            event["ticket_id"] == ticket_id and event["event_type"] == event_type
            for event in repository.added_events
        )

    async def list_for_ticket(*, ticket_id: int) -> list[SimpleNamespace]:
        return [
            event
            for event in repository.listed_events
            if getattr(event, "ticket_id", None) in {None, ticket_id}
        ]

    repository.add = AsyncMock(side_effect=add)
    repository.exists = AsyncMock(side_effect=exists)
    repository.list_for_ticket = AsyncMock(side_effect=list_for_ticket)
    return repository


def build_operator_repository_mock(operator_ids: dict[int, int]) -> Mock:
    repository = Mock()
    repository.calls = []

    async def get_or_create(
        *,
        telegram_user_id: int,
        display_name: str,
        username: str | None = None,
    ) -> int:
        repository.calls.append(
            {
                "telegram_user_id": telegram_user_id,
                "display_name": display_name,
                "username": username,
            }
        )
        return operator_ids[telegram_user_id]

    repository.get_or_create = AsyncMock(side_effect=get_or_create)
    return repository


@dataclass
class StubTicketFeedbackRepository:
    initial_feedback: list[SimpleNamespace] | None = None

    def __post_init__(self) -> None:
        self.get_calls: list[int] = []
        self.create_calls: list[dict[str, object]] = []
        self.update_comment_calls: list[dict[str, object]] = []
        active_feedback = [] if self.initial_feedback is None else list(self.initial_feedback)
        self.records_by_ticket_id = {
            int(record.ticket_id): record
            for record in active_feedback
            if record.ticket_id is not None
        }
        self.next_id = max((int(record.id) for record in active_feedback), default=0) + 1

    async def get_by_ticket_id(self, *, ticket_id: int) -> SimpleNamespace | None:
        self.get_calls.append(ticket_id)
        return self.records_by_ticket_id.get(ticket_id)

    async def create(
        self,
        *,
        ticket_id: int,
        client_chat_id: int,
        rating: int,
    ) -> SimpleNamespace:
        self.create_calls.append(
            {
                "ticket_id": ticket_id,
                "client_chat_id": client_chat_id,
                "rating": rating,
            }
        )
        existing = self.records_by_ticket_id.get(ticket_id)
        if existing is not None:
            return existing

        record = SimpleNamespace(
            id=self.next_id,
            ticket_id=ticket_id,
            client_chat_id=client_chat_id,
            rating=rating,
            comment=None,
            submitted_at=datetime.now(UTC),
        )
        self.next_id += 1
        self.records_by_ticket_id[ticket_id] = record
        return record

    async def update_comment(
        self,
        *,
        ticket_id: int,
        comment: str,
    ) -> SimpleNamespace | None:
        self.update_comment_calls.append(
            {
                "ticket_id": ticket_id,
                "comment": comment,
            }
        )
        record = self.records_by_ticket_id.get(ticket_id)
        if record is None:
            return None
        record.comment = comment
        return record


@dataclass
class StubOperatorManagementRepository:
    active_operator_ids: set[int] = field(default_factory=set)
    display_names: dict[int, str] = field(default_factory=dict)
    usernames: dict[int, str | None] = field(default_factory=dict)

    async def exists_active_by_telegram_user_id(self, *, telegram_user_id: int) -> bool:
        return telegram_user_id in self.active_operator_ids

    async def list_active(self) -> list[SimpleNamespace]:
        return [
            SimpleNamespace(
                id=index,
                telegram_user_id=telegram_user_id,
                username=self.usernames.get(telegram_user_id),
                display_name=self.display_names.get(
                    telegram_user_id, f"Оператор {telegram_user_id}"
                ),
                is_active=True,
            )
            for index, telegram_user_id in enumerate(sorted(self.active_operator_ids), start=1)
        ]

    async def promote(
        self,
        *,
        telegram_user_id: int,
        display_name: str,
        username: str | None = None,
    ) -> SimpleNamespace:
        self.active_operator_ids.add(telegram_user_id)
        self.display_names[telegram_user_id] = display_name
        if username is not None or telegram_user_id not in self.usernames:
            self.usernames[telegram_user_id] = username
        return SimpleNamespace(
            id=len(self.active_operator_ids),
            telegram_user_id=telegram_user_id,
            username=self.usernames.get(telegram_user_id),
            display_name=display_name,
            is_active=True,
        )

    async def revoke(self, *, telegram_user_id: int) -> SimpleNamespace | None:
        if telegram_user_id not in self.active_operator_ids:
            return None

        self.active_operator_ids.remove(telegram_user_id)
        return SimpleNamespace(
            id=1,
            telegram_user_id=telegram_user_id,
            username=self.usernames.get(telegram_user_id),
            display_name=self.display_names.get(telegram_user_id, f"Оператор {telegram_user_id}"),
            is_active=False,
        )

    async def get_or_create(
        self,
        *,
        telegram_user_id: int,
        display_name: str,
        username: str | None = None,
    ) -> int:
        self.active_operator_ids.add(telegram_user_id)
        self.display_names[telegram_user_id] = display_name
        if username is not None or telegram_user_id not in self.usernames:
            self.usernames[telegram_user_id] = username
        return telegram_user_id


def build_macro_repository_mock(
    macros: list[SimpleNamespace] | None = None,
) -> Mock:
    repository = Mock()
    active_macros = [] if macros is None else macros
    next_id = max((int(macro.id) for macro in active_macros), default=0) + 1

    async def list_all() -> list[SimpleNamespace]:
        return sorted(active_macros, key=lambda macro: (macro.title, macro.id))

    async def get_by_id(*, macro_id: int) -> SimpleNamespace | None:
        for macro in active_macros:
            if macro.id == macro_id:
                return macro
        return None

    async def get_by_title(*, title: str) -> SimpleNamespace | None:
        for macro in active_macros:
            if macro.title == title:
                return macro
        return None

    async def create(*, title: str, body: str) -> SimpleNamespace:
        nonlocal next_id
        macro = SimpleNamespace(id=next_id, title=title, body=body)
        next_id += 1
        active_macros.append(macro)
        return macro

    async def update_title(*, macro_id: int, title: str) -> SimpleNamespace | None:
        macro = await get_by_id(macro_id=macro_id)
        if macro is None:
            return None
        macro.title = title
        return macro

    async def update_body(*, macro_id: int, body: str) -> SimpleNamespace | None:
        macro = await get_by_id(macro_id=macro_id)
        if macro is None:
            return None
        macro.body = body
        return macro

    async def delete(*, macro_id: int) -> SimpleNamespace | None:
        macro = await get_by_id(macro_id=macro_id)
        if macro is None:
            return None
        active_macros.remove(macro)
        return macro

    repository.list_all = AsyncMock(side_effect=list_all)
    repository.get_by_id = AsyncMock(side_effect=get_by_id)
    repository.get_by_title = AsyncMock(side_effect=get_by_title)
    repository.create = AsyncMock(side_effect=create)
    repository.update_title = AsyncMock(side_effect=update_title)
    repository.update_body = AsyncMock(side_effect=update_body)
    repository.delete = AsyncMock(side_effect=delete)
    return repository


def build_sla_policy_repository_mock(
    policies: dict[TicketPriority | None, SimpleNamespace],
) -> Mock:
    repository = Mock()
    repository.calls = []

    async def get_for_priority(
        *,
        priority: TicketPriority,
    ) -> SimpleNamespace | None:
        repository.calls.append(priority)
        return policies.get(priority) or policies.get(None)

    repository.get_for_priority = AsyncMock(side_effect=get_for_priority)
    return repository


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
        return int(record.id)

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


@dataclass
class StubTicketCategoryRepository:
    initial_categories: list[tuple[int, str, str, bool, int]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.records_by_id: dict[int, SimpleNamespace] = {}
        self.records_by_code: dict[str, SimpleNamespace] = {}
        self.next_id = 1
        for category_id, code, title, is_active, sort_order in self.initial_categories:
            record = SimpleNamespace(
                id=category_id,
                code=code,
                title=title,
                is_active=is_active,
                sort_order=sort_order,
            )
            self.records_by_id[category_id] = record
            self.records_by_code[code] = record
            self.next_id = max(self.next_id, category_id + 1)

    async def list_all(self, *, include_inactive: bool = True) -> list[SimpleNamespace]:
        items = sorted(
            self.records_by_id.values(),
            key=lambda category: (category.sort_order, category.title, category.id),
        )
        if include_inactive:
            return items
        return [category for category in items if category.is_active]

    async def get_by_id(self, *, category_id: int) -> SimpleNamespace | None:
        return self.records_by_id.get(category_id)

    async def get_by_code(self, *, code: str) -> SimpleNamespace | None:
        return self.records_by_code.get(code)

    async def create(
        self,
        *,
        code: str,
        title: str,
        sort_order: int,
        is_active: bool = True,
    ) -> SimpleNamespace:
        record = SimpleNamespace(
            id=self.next_id,
            code=code,
            title=title,
            is_active=is_active,
            sort_order=sort_order,
        )
        self.next_id += 1
        self.records_by_id[record.id] = record
        self.records_by_code[record.code] = record
        return record

    async def update_title(self, *, category_id: int, title: str) -> SimpleNamespace | None:
        record = self.records_by_id.get(category_id)
        if record is None:
            return None
        record.title = title
        return record

    async def set_active(
        self,
        *,
        category_id: int,
        is_active: bool,
    ) -> SimpleNamespace | None:
        record = self.records_by_id.get(category_id)
        if record is None:
            return None
        record.is_active = is_active
        return record

    async def get_next_sort_order(self) -> int:
        current_max = max(
            (category.sort_order for category in self.records_by_id.values()),
            default=0,
        )
        return current_max + 10


def build_ticket(
    *,
    ticket_id: int,
    public_id: UUID,
    status: TicketStatus,
    assigned_operator_id: int | None = None,
    assigned_operator_name: str | None = None,
    assigned_operator_telegram_user_id: int | None = None,
    last_message_text: str | None = None,
    last_message_sender_type: TicketMessageSenderType | None = None,
    message_history: tuple[TicketMessageDetails, ...] = (),
    tags: tuple[str, ...] = (),
    category_id: int | None = None,
    category_code: str | None = None,
    category_title: str | None = None,
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
        category_id=category_id,
        assigned_operator_id=assigned_operator_id,
        created_at=created_at or now,
        updated_at=updated_at or now,
        first_response_at=first_response_at,
        closed_at=closed_at,
        assigned_operator_name=assigned_operator_name,
        assigned_operator_telegram_user_id=assigned_operator_telegram_user_id,
        category_code=category_code,
        category_title=category_title,
        last_message_text=last_message_text,
        last_message_sender_type=last_message_sender_type,
        message_history=message_history,
        tags=tags,
    )


def build_service(
    *,
    ticket_repository: StubTicketRepository,
    ticket_feedback_repository: StubTicketFeedbackRepository | None = None,
    message_repository: Any | None = None,
    event_repository: Any | None = None,
    operator_repository: Any | None = None,
    macro_repository: Any | None = None,
    sla_policy_repository: Any | None = None,
    tag_repository: StubTagRepository | None = None,
    ticket_category_repository: StubTicketCategoryRepository | None = None,
    ticket_tag_repository: StubTicketTagRepository | None = None,
    super_admin_telegram_user_ids: frozenset[int] | None = None,
) -> HelpdeskService:
    active_tag_repository = tag_repository or StubTagRepository()
    return HelpdeskService(
        ticket_repository=ticket_repository,
        ticket_feedback_repository=ticket_feedback_repository or StubTicketFeedbackRepository(),
        ticket_message_repository=message_repository or build_message_repository_mock(),
        ticket_event_repository=event_repository or build_event_repository_mock(),
        operator_repository=operator_repository or build_operator_repository_mock({}),
        macro_repository=macro_repository or build_macro_repository_mock(),
        sla_policy_repository=sla_policy_repository
        or build_sla_policy_repository_mock(
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
        ticket_category_repository=ticket_category_repository
        or StubTicketCategoryRepository(
            initial_categories=[
                (1, "access", "Доступ и вход", True, 10),
                (2, "other", "Другая тема", True, 90),
            ]
        ),
        ticket_tag_repository=ticket_tag_repository
        or StubTicketTagRepository(tag_repository=active_tag_repository),
        super_admin_telegram_user_ids=super_admin_telegram_user_ids or frozenset({42}),
    )


async def test_create_ticket_from_first_client_message_creates_queues_and_logs_events() -> None:
    public_id = uuid4()
    created_ticket = build_ticket(ticket_id=1, public_id=public_id, status=TicketStatus.NEW)
    ticket_repository = StubTicketRepository(created_ticket=created_ticket)
    message_repository = build_message_repository_mock()
    event_repository = build_event_repository_mock()
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
    message_repository = build_message_repository_mock()
    event_repository = build_event_repository_mock()
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


async def test_create_ticket_from_client_intake_persists_selected_category() -> None:
    public_id = uuid4()
    created_ticket = build_ticket(ticket_id=1, public_id=public_id, status=TicketStatus.NEW)
    ticket_repository = StubTicketRepository(created_ticket=created_ticket)
    service = build_service(ticket_repository=ticket_repository)

    result = await service.create_ticket_from_client_intake(
        client_chat_id=555,
        telegram_message_id=777,
        category_id=2,
        text="Нужна помощь с другим вопросом",
    )

    assert result.public_id == public_id
    assert ticket_repository.create_calls[0]["category_id"] == 2
    assert created_ticket.category_id == 2


async def test_add_operator_message_logs_event_and_sets_first_response_timestamp() -> None:
    public_id = uuid4()
    ticket = build_ticket(ticket_id=1, public_id=public_id, status=TicketStatus.ASSIGNED)
    message_repository = build_message_repository_mock()
    event_repository = build_event_repository_mock()
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
    event_repository = build_event_repository_mock()
    operator_repository = build_operator_repository_mock({1001: 7, 1002: 9})
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


async def test_list_operators_returns_active_operator_summaries() -> None:
    operator_repository = StubOperatorManagementRepository(
        active_operator_ids={1001, 1002},
        display_names={1001: "Иван", 1002: "Мария"},
        usernames={1001: "ivan", 1002: None},
    )
    service = build_service(
        ticket_repository=StubTicketRepository(
            created_ticket=build_ticket(
                ticket_id=1,
                public_id=uuid4(),
                status=TicketStatus.NEW,
            )
        ),
        operator_repository=operator_repository,
    )

    result = await service.list_operators()

    assert [(operator.telegram_user_id, operator.display_name) for operator in result] == [
        (1001, "Иван"),
        (1002, "Мария"),
    ]


async def test_list_operators_rejects_non_admin_actor_when_actor_is_provided() -> None:
    operator_repository = StubOperatorManagementRepository(
        active_operator_ids={1001},
        display_names={1001: "Иван"},
    )
    service = build_service(
        ticket_repository=StubTicketRepository(
            created_ticket=build_ticket(
                ticket_id=1,
                public_id=uuid4(),
                status=TicketStatus.NEW,
            )
        ),
        operator_repository=operator_repository,
        super_admin_telegram_user_ids=frozenset({42}),
    )

    try:
        await service.list_operators(actor_telegram_user_id=1001)
    except AuthorizationError as exc:
        assert str(exc) == "Доступно только суперадминистраторам."
    else:
        raise AssertionError("expected AuthorizationError")


async def test_promote_operator_marks_user_as_operator() -> None:
    operator_repository = StubOperatorManagementRepository()
    service = build_service(
        ticket_repository=StubTicketRepository(
            created_ticket=build_ticket(
                ticket_id=1,
                public_id=uuid4(),
                status=TicketStatus.NEW,
            )
        ),
        operator_repository=operator_repository,
    )

    result = await service.promote_operator(
        telegram_user_id=3001,
        display_name="Новый оператор",
    )

    assert result.changed is True
    assert result.operator.telegram_user_id == 3001
    assert 3001 in operator_repository.active_operator_ids


async def test_list_client_ticket_categories_returns_only_active_items_in_order() -> None:
    category_repository = StubTicketCategoryRepository(
        initial_categories=[
            (3, "other", "Другая тема", True, 90),
            (1, "access", "Доступ и вход", True, 10),
            (2, "billing", "Оплата", False, 20),
        ]
    )
    service = build_service(
        ticket_repository=StubTicketRepository(
            created_ticket=build_ticket(ticket_id=1, public_id=uuid4(), status=TicketStatus.NEW)
        ),
        ticket_category_repository=category_repository,
    )

    result = await service.list_client_ticket_categories()

    assert [(category.code, category.title) for category in result] == [
        ("access", "Доступ и вход"),
        ("other", "Другая тема"),
    ]


async def test_ticket_category_management_supports_create_rename_and_toggle() -> None:
    category_repository = StubTicketCategoryRepository(
        initial_categories=[(1, "access", "Доступ и вход", True, 10)]
    )
    service = build_service(
        ticket_repository=StubTicketRepository(
            created_ticket=build_ticket(ticket_id=1, public_id=uuid4(), status=TicketStatus.NEW)
        ),
        ticket_category_repository=category_repository,
    )

    created = await service.create_ticket_category(title="Техническая ошибка")
    renamed = await service.update_ticket_category_title(
        category_id=created.id,
        title="Технический сбой",
    )
    disabled = await service.set_ticket_category_active(
        category_id=created.id,
        is_active=False,
    )

    assert created.code == "tehnicheskaya-oshibka"
    assert renamed is not None
    assert renamed.title == "Технический сбой"
    assert disabled is not None
    assert disabled.is_active is False


async def test_ticket_category_creation_rejects_empty_title() -> None:
    service = build_service(
        ticket_repository=StubTicketRepository(
            created_ticket=build_ticket(ticket_id=1, public_id=uuid4(), status=TicketStatus.NEW)
        )
    )

    try:
        await service.create_ticket_category(title="   ")
    except CategoryManagementError as exc:
        assert str(exc) == "Название темы не должно быть пустым."
    else:
        raise AssertionError("expected CategoryManagementError")


async def test_revoke_operator_removes_operator_rights() -> None:
    operator_repository = StubOperatorManagementRepository(
        active_operator_ids={3001},
        display_names={3001: "Оператор 3001"},
    )
    service = build_service(
        ticket_repository=StubTicketRepository(
            created_ticket=build_ticket(
                ticket_id=1,
                public_id=uuid4(),
                status=TicketStatus.NEW,
            )
        ),
        operator_repository=operator_repository,
    )

    result = await service.revoke_operator(telegram_user_id=3001)

    assert result is not None
    assert result.operator.is_active is False
    assert 3001 not in operator_repository.active_operator_ids


async def test_revoke_operator_rejects_super_admin_target() -> None:
    service = build_service(
        ticket_repository=StubTicketRepository(
            created_ticket=build_ticket(
                ticket_id=1,
                public_id=uuid4(),
                status=TicketStatus.NEW,
            )
        ),
        operator_repository=StubOperatorManagementRepository(),
        super_admin_telegram_user_ids=frozenset({42}),
    )

    try:
        await service.revoke_operator(telegram_user_id=42)
    except OperatorManagementError as exc:
        assert str(exc) == "Нельзя снять роль у суперадминистратора."
    else:
        raise AssertionError("expected OperatorManagementError")


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
    event_repository = build_event_repository_mock()
    service = build_service(
        ticket_repository=StubTicketRepository(
            created_ticket=build_ticket(ticket_id=3, public_id=uuid4(), status=TicketStatus.NEW),
            queued_tickets=[first_ticket, second_ticket],
        ),
        event_repository=event_repository,
        operator_repository=build_operator_repository_mock({1001: 7}),
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


async def test_assign_next_ticket_to_operator_rejects_regular_user_actor() -> None:
    queued_ticket = build_ticket(ticket_id=1, public_id=uuid4(), status=TicketStatus.QUEUED)
    service = build_service(
        ticket_repository=StubTicketRepository(
            created_ticket=build_ticket(ticket_id=2, public_id=uuid4(), status=TicketStatus.NEW),
            queued_tickets=[queued_ticket],
        ),
        operator_repository=StubOperatorManagementRepository(active_operator_ids=set()),
        super_admin_telegram_user_ids=frozenset({42}),
    )

    try:
        await service.assign_next_ticket_to_operator(
            telegram_user_id=2002,
            display_name="Regular User",
            actor_telegram_user_id=2002,
        )
    except AuthorizationError as exc:
        assert str(exc) == "Доступно только операторам и суперадминистраторам."
    else:
        raise AssertionError("expected AuthorizationError")


async def test_get_operational_stats_returns_aggregated_metrics() -> None:
    ticket_repository = StubTicketRepository(
        created_ticket=build_ticket(ticket_id=1, public_id=uuid4(), status=TicketStatus.NEW),
        by_status={
            TicketStatus.QUEUED: 2,
            TicketStatus.ASSIGNED: 3,
            TicketStatus.ESCALATED: 1,
            TicketStatus.CLOSED: 4,
        },
        active_operator_ticket_loads=[
            SimpleNamespace(operator_id=7, display_name="Operator One", ticket_count=3),
            SimpleNamespace(operator_id=9, display_name="Operator Two", ticket_count=1),
        ],
        average_first_response_time_seconds=125.6,
        average_resolution_time_seconds=7260.4,
    )
    service = build_service(ticket_repository=ticket_repository)

    stats = await service.get_operational_stats()

    assert stats.total_open_tickets == 6
    assert stats.queued_tickets_count == 2
    assert stats.assigned_tickets_count == 3
    assert stats.escalated_tickets_count == 1
    assert stats.closed_tickets_count == 4
    assert stats.tickets_per_operator[0].display_name == "Operator One"
    assert stats.tickets_per_operator[0].ticket_count == 3
    assert stats.average_first_response_time_seconds == 126
    assert stats.average_resolution_time_seconds == 7260
    assert ticket_repository.count_active_tickets_per_operator_calls == 1
    assert ticket_repository.average_first_response_calls == 1
    assert ticket_repository.average_resolution_calls == 1


async def test_service_supports_main_ticket_lifecycle_and_stats() -> None:
    public_id = uuid4()
    ticket = build_ticket(ticket_id=1, public_id=public_id, status=TicketStatus.NEW)
    ticket_repository = StubTicketRepository(
        created_ticket=ticket,
        queued_tickets=[ticket],
    )
    message_repository = build_message_repository_mock()
    event_repository = build_event_repository_mock()
    service = build_service(
        ticket_repository=ticket_repository,
        message_repository=message_repository,
        event_repository=event_repository,
        operator_repository=build_operator_repository_mock({1001: 7}),
    )

    created = await service.create_ticket_from_client_message(
        client_chat_id=555,
        telegram_message_id=7001,
        text="Cannot log in",
    )
    taken = await service.assign_next_ticket_to_operator(
        telegram_user_id=1001,
        display_name="Operator One",
    )
    reply = await service.reply_to_ticket_as_operator(
        ticket_public_id=public_id,
        telegram_user_id=1001,
        display_name="Operator One",
        username="operator_one",
        telegram_message_id=7002,
        text="Please try again now.",
    )
    closed = await service.close_ticket(ticket_public_id=public_id)

    ticket_repository.by_status = {TicketStatus.CLOSED: 1}
    stats = await service.get_operational_stats()

    assert created.public_id == public_id
    assert created.status == TicketStatus.QUEUED
    assert taken is not None
    assert taken.status == TicketStatus.ASSIGNED
    assert reply is not None
    assert reply.ticket.public_id == public_id
    assert closed is not None
    assert closed.status == TicketStatus.CLOSED
    assert stats.total_open_tickets == 0
    assert stats.closed_tickets_count == 1
    assert [event["event_type"] for event in event_repository.added_events] == [
        TicketEventType.CREATED,
        TicketEventType.QUEUED,
        TicketEventType.CLIENT_MESSAGE_ADDED,
        TicketEventType.ASSIGNED,
        TicketEventType.OPERATOR_MESSAGE_ADDED,
        TicketEventType.CLOSED,
    ]


async def test_reply_to_ticket_as_operator_rejects_closed_ticket() -> None:
    public_id = uuid4()
    ticket = build_ticket(ticket_id=1, public_id=public_id, status=TicketStatus.CLOSED)
    message_repository = build_message_repository_mock()
    event_repository = build_event_repository_mock()
    service = build_service(
        ticket_repository=StubTicketRepository(created_ticket=ticket),
        message_repository=message_repository,
        event_repository=event_repository,
        operator_repository=build_operator_repository_mock({1001: 7}),
    )

    try:
        await service.reply_to_ticket_as_operator(
            ticket_public_id=public_id,
            telegram_user_id=1001,
            display_name="Operator One",
            username="operator_one",
            telegram_message_id=4321,
            text="Please try again now.",
        )
    except InvalidTicketTransitionError as exc:
        assert "закры" in str(exc).lower()
    else:
        raise AssertionError("Expected InvalidTicketTransitionError for closed ticket reply")

    assert message_repository.added_messages == []
    assert event_repository.added_events == []


async def test_close_ticket_rejects_already_closed_ticket() -> None:
    public_id = uuid4()
    ticket = build_ticket(ticket_id=1, public_id=public_id, status=TicketStatus.CLOSED)
    event_repository = build_event_repository_mock()
    service = build_service(
        ticket_repository=StubTicketRepository(created_ticket=ticket),
        event_repository=event_repository,
    )

    try:
        await service.close_ticket(ticket_public_id=public_id)
    except InvalidTicketTransitionError as exc:
        assert "закры" in str(exc).lower()
    else:
        raise AssertionError("Expected InvalidTicketTransitionError for closed ticket")

    assert event_repository.added_events == []


async def test_submit_ticket_feedback_rating_creates_feedback_for_closed_ticket() -> None:
    public_id = uuid4()
    ticket = build_ticket(ticket_id=1, public_id=public_id, status=TicketStatus.CLOSED)
    feedback_repository = StubTicketFeedbackRepository()
    service = build_service(
        ticket_repository=StubTicketRepository(created_ticket=ticket),
        ticket_feedback_repository=feedback_repository,
    )

    result = await service.submit_ticket_feedback_rating(
        ticket_public_id=public_id,
        client_chat_id=ticket.client_chat_id,
        rating=5,
    )

    assert result.status.value == "created"
    assert result.feedback is not None
    assert result.feedback.rating == 5
    assert result.feedback.public_id == public_id
    assert feedback_repository.create_calls == [
        {
            "ticket_id": ticket.id,
            "client_chat_id": ticket.client_chat_id,
            "rating": 5,
        }
    ]


async def test_submit_ticket_feedback_rating_returns_existing_feedback_without_duplicate() -> None:
    public_id = uuid4()
    ticket = build_ticket(ticket_id=1, public_id=public_id, status=TicketStatus.CLOSED)
    existing_feedback = SimpleNamespace(
        id=3,
        ticket_id=ticket.id,
        client_chat_id=ticket.client_chat_id,
        rating=4,
        comment=None,
        submitted_at=datetime.now(UTC),
    )
    feedback_repository = StubTicketFeedbackRepository(initial_feedback=[existing_feedback])
    service = build_service(
        ticket_repository=StubTicketRepository(created_ticket=ticket),
        ticket_feedback_repository=feedback_repository,
    )

    result = await service.submit_ticket_feedback_rating(
        ticket_public_id=public_id,
        client_chat_id=ticket.client_chat_id,
        rating=5,
    )

    assert result.status.value == "already_recorded"
    assert result.feedback is not None
    assert result.feedback.rating == 4
    assert feedback_repository.create_calls == []


async def test_add_ticket_feedback_comment_updates_existing_feedback() -> None:
    public_id = uuid4()
    ticket = build_ticket(ticket_id=1, public_id=public_id, status=TicketStatus.CLOSED)
    existing_feedback = SimpleNamespace(
        id=3,
        ticket_id=ticket.id,
        client_chat_id=ticket.client_chat_id,
        rating=5,
        comment=None,
        submitted_at=datetime.now(UTC),
    )
    feedback_repository = StubTicketFeedbackRepository(initial_feedback=[existing_feedback])
    service = build_service(
        ticket_repository=StubTicketRepository(created_ticket=ticket),
        ticket_feedback_repository=feedback_repository,
    )

    result = await service.add_ticket_feedback_comment(
        ticket_public_id=public_id,
        client_chat_id=ticket.client_chat_id,
        comment="Спасибо за помощь",
    )

    assert result.status.value == "updated"
    assert result.feedback is not None
    assert result.feedback.comment == "Спасибо за помощь"
    assert feedback_repository.update_comment_calls == [
        {
            "ticket_id": ticket.id,
            "comment": "Спасибо за помощь",
        }
    ]


async def test_get_ticket_details_returns_operator_facing_summary_with_tags() -> None:
    public_id = uuid4()
    ticket = build_ticket(
        ticket_id=1,
        public_id=public_id,
        status=TicketStatus.ASSIGNED,
        assigned_operator_id=7,
        assigned_operator_name="Operator One",
        assigned_operator_telegram_user_id=1001,
        last_message_text="Client says hello",
        last_message_sender_type=TicketMessageSenderType.CLIENT,
        message_history=(
            TicketMessageDetails(
                telegram_message_id=11,
                sender_type=TicketMessageSenderType.CLIENT,
                sender_operator_id=None,
                sender_operator_name=None,
                text="Client says hello",
                created_at=datetime.now(UTC),
            ),
        ),
        tags=("billing", "vip"),
        category_id=1,
        category_code="access",
        category_title="Доступ и вход",
    )
    service = build_service(ticket_repository=StubTicketRepository(created_ticket=ticket))

    result = await service.get_ticket_details(ticket_public_id=public_id)

    assert result is not None
    assert result.public_id == public_id
    assert result.public_number.startswith("HD-")
    assert result.assigned_operator_name == "Operator One"
    assert result.assigned_operator_telegram_user_id == 1001
    assert result.category_title == "Доступ и вход"
    assert result.last_message_text == "Client says hello"
    assert result.last_message_sender_type == TicketMessageSenderType.CLIENT
    assert result.message_history[0].text == "Client says hello"
    assert result.tags == ("billing", "vip")


async def test_export_ticket_report_returns_csv_with_metadata_feedback_and_history() -> None:
    public_id = uuid4()
    created_at = datetime(2026, 4, 8, 9, 0, tzinfo=UTC)
    first_response_at = created_at + timedelta(minutes=12)
    updated_at = created_at + timedelta(minutes=40)
    closed_at = created_at + timedelta(hours=2)
    ticket = build_ticket(
        ticket_id=1,
        public_id=public_id,
        status=TicketStatus.CLOSED,
        assigned_operator_id=7,
        assigned_operator_name="Operator One",
        assigned_operator_telegram_user_id=1001,
        message_history=(
            TicketMessageDetails(
                telegram_message_id=11,
                sender_type=TicketMessageSenderType.CLIENT,
                sender_operator_id=None,
                sender_operator_name=None,
                text="Не могу войти в кабинет",
                created_at=created_at,
            ),
            TicketMessageDetails(
                telegram_message_id=12,
                sender_type=TicketMessageSenderType.OPERATOR,
                sender_operator_id=7,
                sender_operator_name="Operator One",
                text="Доступ уже восстановлен",
                created_at=first_response_at,
            ),
        ),
        tags=("vip",),
        category_code="access",
        category_title="Доступ и вход",
        created_at=created_at,
        updated_at=updated_at,
        first_response_at=first_response_at,
        closed_at=closed_at,
    )
    feedback_repository = StubTicketFeedbackRepository(
        initial_feedback=[
            SimpleNamespace(
                id=1,
                ticket_id=1,
                client_chat_id=ticket.client_chat_id,
                rating=5,
                comment="Спасибо",
                submitted_at=closed_at + timedelta(minutes=5),
            )
        ]
    )
    event_repository = build_event_repository_mock(
        initial_events=[
            SimpleNamespace(
                ticket_id=1,
                event_type=TicketEventType.CREATED,
                payload_json={"status": "new"},
                created_at=created_at,
            ),
            SimpleNamespace(
                ticket_id=1,
                event_type=TicketEventType.CLOSED,
                payload_json={"from_status": "assigned", "to_status": "closed"},
                created_at=closed_at,
            ),
        ]
    )
    service = build_service(
        ticket_repository=StubTicketRepository(created_ticket=ticket),
        ticket_feedback_repository=feedback_repository,
        event_repository=event_repository,
        operator_repository=StubOperatorManagementRepository(active_operator_ids={1001}),
    )

    result = await service.export_ticket_report(
        ticket_public_id=public_id,
        format=TicketReportFormat.CSV,
        actor_telegram_user_id=1001,
    )

    assert result is not None
    assert result.filename.endswith(".csv")
    content = result.content.decode("utf-8-sig")
    assert "ticket_public_number" in content
    assert "ticket_status" in content
    assert "Не могу войти в кабинет" in content
    assert "Доступ уже восстановлен" in content
    assert "Спасибо" in content
    assert "closed" in content


async def test_export_ticket_report_returns_html_with_sections() -> None:
    public_id = uuid4()
    created_at = datetime(2026, 4, 8, 9, 0, tzinfo=UTC)
    ticket = build_ticket(
        ticket_id=1,
        public_id=public_id,
        status=TicketStatus.ASSIGNED,
        assigned_operator_id=7,
        assigned_operator_name="Operator One",
        assigned_operator_telegram_user_id=1001,
        message_history=(
            TicketMessageDetails(
                telegram_message_id=11,
                sender_type=TicketMessageSenderType.CLIENT,
                sender_operator_id=None,
                sender_operator_name=None,
                text="Нужна помощь с доступом",
                created_at=created_at,
            ),
        ),
        tags=("vip", "billing"),
        category_code="access",
        category_title="Доступ и вход",
        created_at=created_at,
        updated_at=created_at + timedelta(minutes=25),
    )
    service = build_service(
        ticket_repository=StubTicketRepository(created_ticket=ticket),
        operator_repository=StubOperatorManagementRepository(active_operator_ids={1001}),
    )

    result = await service.export_ticket_report(
        ticket_public_id=public_id,
        format=TicketReportFormat.HTML,
        actor_telegram_user_id=1001,
    )

    assert result is not None
    assert result.filename.endswith(".html")
    content = result.content.decode("utf-8")
    assert "<html" in content
    assert "Карточка" in content
    assert "Переписка" in content
    assert "Нужна помощь с доступом" in content
    assert "HD-" in content


async def test_reply_to_ticket_as_operator_persists_message_and_returns_client_chat() -> None:
    public_id = uuid4()
    ticket = build_ticket(
        ticket_id=1,
        public_id=public_id,
        status=TicketStatus.ASSIGNED,
        assigned_operator_id=7,
    )
    message_repository = build_message_repository_mock()
    event_repository = build_event_repository_mock()
    service = build_service(
        ticket_repository=StubTicketRepository(created_ticket=ticket),
        message_repository=message_repository,
        event_repository=event_repository,
        operator_repository=build_operator_repository_mock({1001: 7}),
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
        macro_repository=build_macro_repository_mock(
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
    message_repository = build_message_repository_mock(next_internal_message_id=-11)
    event_repository = build_event_repository_mock()
    service = build_service(
        ticket_repository=StubTicketRepository(created_ticket=ticket),
        message_repository=message_repository,
        event_repository=event_repository,
        operator_repository=build_operator_repository_mock({1001: 7}),
        macro_repository=build_macro_repository_mock(
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
    macro_event_payload = event_repository.added_events[0]["payload_json"]
    assert isinstance(macro_event_payload, dict)
    assert macro_event_payload["macro_id"] == 5
    assert macro_event_payload["macro_title"] == "Resolved"


async def test_super_admin_can_create_update_and_delete_macro() -> None:
    macro_repository = build_macro_repository_mock(
        macros=[SimpleNamespace(id=5, title="Resolved", body="Issue resolved.")]
    )
    service = build_service(
        ticket_repository=StubTicketRepository(
            created_ticket=build_ticket(ticket_id=1, public_id=uuid4(), status=TicketStatus.NEW)
        ),
        macro_repository=macro_repository,
        super_admin_telegram_user_ids=frozenset({42}),
    )

    created = await service.create_macro(
        title="Новый макрос",
        body="Готово.",
        actor_telegram_user_id=42,
    )
    updated_title = await service.update_macro_title(
        macro_id=created.id,
        title="Финальный ответ",
        actor_telegram_user_id=42,
    )
    updated_body = await service.update_macro_body(
        macro_id=created.id,
        body="Проверили. Всё исправлено.",
        actor_telegram_user_id=42,
    )
    deleted = await service.delete_macro(
        macro_id=created.id,
        actor_telegram_user_id=42,
    )

    assert created.title == "Новый макрос"
    assert updated_title is not None
    assert updated_title.title == "Финальный ответ"
    assert updated_body is not None
    assert updated_body.body == "Проверили. Всё исправлено."
    assert deleted is not None
    assert deleted.id == created.id


async def test_create_macro_rejects_duplicate_title() -> None:
    service = build_service(
        ticket_repository=StubTicketRepository(
            created_ticket=build_ticket(ticket_id=1, public_id=uuid4(), status=TicketStatus.NEW)
        ),
        macro_repository=build_macro_repository_mock(
            macros=[SimpleNamespace(id=5, title="Resolved", body="Issue resolved.")]
        ),
        super_admin_telegram_user_ids=frozenset({42}),
    )

    try:
        await service.create_macro(
            title="Resolved",
            body="Another body",
            actor_telegram_user_id=42,
        )
    except MacroManagementError as exc:
        assert str(exc) == "Макрос с таким названием уже есть."
    else:
        raise AssertionError("expected MacroManagementError")


async def test_add_tag_to_ticket_is_idempotent_and_logs_event_once() -> None:
    public_id = uuid4()
    ticket = build_ticket(ticket_id=1, public_id=public_id, status=TicketStatus.ASSIGNED)
    tag_repository = StubTagRepository(initial_tags=[(10, "vip")])
    ticket_tag_repository = StubTicketTagRepository(tag_repository=tag_repository)
    event_repository = build_event_repository_mock()
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
    event_repository = build_event_repository_mock()
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
    assert available_tags == [
        TagSummary(id=11, name="billing"),
        TagSummary(id=10, name="vip"),
    ]


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
