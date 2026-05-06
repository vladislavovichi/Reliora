from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

from application.contracts.actors import OperatorIdentity, RequestActor
from application.contracts.ai import AIServiceClientFactory, AnalyzedTicketSentimentResult
from application.contracts.tickets import (
    ApplyMacroToTicketCommand,
    AssignNextQueuedTicketCommand,
    ClientTicketMessageCommand,
    OperatorTicketReplyCommand,
    TicketAssignmentCommand,
)
from application.services.authorization import AuthorizationError
from application.services.helpdesk.components import HelpdeskExportRenderers
from application.services.helpdesk.service import HelpdeskService
from application.services.stats import AnalyticsWindow
from application.use_cases.tickets.exports import TicketReportFormat
from application.use_cases.tickets.operator_invites import OPERATOR_INVITE_PREFIX
from application.use_cases.tickets.summaries import (
    CategoryManagementError,
    MacroManagementError,
    OperatorManagementError,
    TagSummary,
)
from domain.entities.ticket import (
    TicketAttachmentDetails,
    TicketDetails,
    TicketHistoryEntry,
    TicketMessageDetails,
)
from domain.enums.tickets import (
    TicketAttachmentKind,
    TicketEventType,
    TicketMessageSenderType,
    TicketPriority,
    TicketSentiment,
    TicketSignalConfidence,
    TicketStatus,
)
from domain.tickets import InvalidTicketTransitionError
from infrastructure.exports.analytics_snapshot_csv import render_analytics_snapshot_csv
from infrastructure.exports.analytics_snapshot_html import render_analytics_snapshot_html
from infrastructure.exports.ticket_report_csv import render_ticket_report_csv
from infrastructure.exports.ticket_report_html import render_ticket_report_html
from tests.fakes.ai import StubSentimentAIClient, build_ai_client_factory


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
    created_tickets_count: int = 0
    closed_tickets_count: int = 0
    feedback_submissions_count: int = 0
    average_feedback_rating: float | None = None
    feedback_rating_distribution: list[SimpleNamespace] | None = None
    operator_closure_stats: list[SimpleNamespace] | None = None
    created_ticket_category_counts: list[SimpleNamespace] | None = None
    open_ticket_category_counts: list[SimpleNamespace] | None = None
    closed_ticket_category_counts: list[SimpleNamespace] | None = None
    category_feedback_stats: list[SimpleNamespace] | None = None
    sla_breach_counts: dict[str, int] | None = None
    sla_breach_category_counts: list[SimpleNamespace] | None = None

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
        self.created_tickets_calls: list[datetime | None] = []
        self.closed_tickets_calls: list[datetime | None] = []
        self.feedback_submission_calls: list[datetime | None] = []
        self.average_feedback_calls: list[datetime | None] = []
        self.feedback_distribution_calls: list[datetime | None] = []
        self.operator_closure_stats_calls: list[datetime | None] = []
        self.created_category_calls: list[datetime | None] = []
        self.open_category_calls = 0
        self.closed_category_calls: list[datetime | None] = []
        self.category_feedback_calls: list[datetime | None] = []
        self.sla_breach_calls: list[datetime | None] = []
        self.sla_breach_category_calls: list[datetime | None] = []
        self.tickets: dict[UUID, SimpleNamespace] = {
            self.created_ticket.public_id: self.created_ticket,
        }
        if self.active_ticket is not None:
            self.tickets[self.active_ticket.public_id] = self.active_ticket
        if self.queued_tickets is None:
            self.queued_tickets = []
        if self.active_operator_ticket_loads is None:
            self.active_operator_ticket_loads = []
        if self.feedback_rating_distribution is None:
            self.feedback_rating_distribution = []
        if self.operator_closure_stats is None:
            self.operator_closure_stats = []
        if self.created_ticket_category_counts is None:
            self.created_ticket_category_counts = []
        if self.open_ticket_category_counts is None:
            self.open_ticket_category_counts = []
        if self.closed_ticket_category_counts is None:
            self.closed_ticket_category_counts = []
        if self.category_feedback_stats is None:
            self.category_feedback_stats = []
        if self.sla_breach_counts is None:
            self.sla_breach_counts = {}
        if self.sla_breach_category_counts is None:
            self.sla_breach_category_counts = []
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
            assigned_operator_username=getattr(ticket, "assigned_operator_username", None),
            created_at=ticket.created_at,
            updated_at=ticket.updated_at,
            first_response_at=ticket.first_response_at,
            closed_at=ticket.closed_at,
            category_id=getattr(ticket, "category_id", None),
            category_code=getattr(ticket, "category_code", None),
            category_title=getattr(ticket, "category_title", None),
            sentiment=getattr(ticket, "sentiment", None),
            sentiment_confidence=getattr(ticket, "sentiment_confidence", None),
            sentiment_reason=getattr(ticket, "sentiment_reason", None),
            sentiment_detected_at=getattr(ticket, "sentiment_detected_at", None),
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

    async def list_closed_tickets(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[TicketHistoryEntry]:
        tickets = [
            TicketHistoryEntry(
                public_id=ticket.public_id,
                status=ticket.status,
                subject=ticket.subject,
                created_at=ticket.created_at,
                closed_at=ticket.closed_at,
                category_id=getattr(ticket, "category_id", None),
                category_code=getattr(ticket, "category_code", None),
                category_title=getattr(ticket, "category_title", None),
            )
            for ticket in self.tickets.values()
            if ticket.status == TicketStatus.CLOSED
        ]
        tickets.sort(key=lambda ticket: ticket.closed_at or ticket.created_at, reverse=True)
        if limit is None:
            return tickets[offset:]
        return tickets[offset : offset + limit]

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

    async def get_average_first_response_time_seconds(
        self,
        *,
        since: datetime | None = None,
    ) -> float | None:
        self.average_first_response_calls += 1
        return self.average_first_response_time_seconds

    async def get_average_resolution_time_seconds(
        self,
        *,
        since: datetime | None = None,
    ) -> float | None:
        self.average_resolution_calls += 1
        return self.average_resolution_time_seconds

    async def count_created_tickets(self, *, since: datetime | None = None) -> int:
        self.created_tickets_calls.append(since)
        return self.created_tickets_count

    async def count_closed_tickets(self, *, since: datetime | None = None) -> int:
        self.closed_tickets_calls.append(since)
        return self.closed_tickets_count

    async def count_feedback_submissions(self, *, since: datetime | None = None) -> int:
        self.feedback_submission_calls.append(since)
        return self.feedback_submissions_count

    async def get_average_feedback_rating(self, *, since: datetime | None = None) -> float | None:
        self.average_feedback_calls.append(since)
        return self.average_feedback_rating

    async def get_feedback_rating_distribution(
        self,
        *,
        since: datetime | None = None,
    ) -> list[SimpleNamespace]:
        self.feedback_distribution_calls.append(since)
        return list(self.feedback_rating_distribution or [])

    async def list_closed_ticket_stats_by_operator(
        self,
        *,
        since: datetime | None = None,
    ) -> list[SimpleNamespace]:
        self.operator_closure_stats_calls.append(since)
        return list(self.operator_closure_stats or [])

    async def list_created_ticket_counts_by_category(
        self,
        *,
        since: datetime | None = None,
    ) -> list[SimpleNamespace]:
        self.created_category_calls.append(since)
        return list(self.created_ticket_category_counts or [])

    async def list_open_ticket_counts_by_category(self) -> list[SimpleNamespace]:
        self.open_category_calls += 1
        return list(self.open_ticket_category_counts or [])

    async def list_closed_ticket_counts_by_category(
        self,
        *,
        since: datetime | None = None,
    ) -> list[SimpleNamespace]:
        self.closed_category_calls.append(since)
        return list(self.closed_ticket_category_counts or [])

    async def list_feedback_stats_by_category(
        self,
        *,
        since: datetime | None = None,
    ) -> list[SimpleNamespace]:
        self.category_feedback_calls.append(since)
        return list(self.category_feedback_stats or [])

    async def count_sla_breaches(self, *, since: datetime | None = None) -> dict[str, int]:
        self.sla_breach_calls.append(since)
        return dict(self.sla_breach_counts or {})

    async def list_sla_breach_counts_by_category(
        self,
        *,
        since: datetime | None = None,
    ) -> list[SimpleNamespace]:
        self.sla_breach_category_calls.append(since)
        return list(self.sla_breach_category_counts or [])


def build_message_repository_mock(*, next_internal_message_id: int = -1) -> Mock:
    repository = Mock()
    repository.added_messages = []
    repository.allocated_internal_ids = []
    repository.duplicate_marks = []
    repository.recent_messages_by_ticket_id = {}

    async def add(
        *,
        ticket_id: int,
        telegram_message_id: int,
        sender_type: TicketMessageSenderType,
        text: str | None,
        attachment: TicketAttachmentDetails | None = None,
        sender_operator_id: int | None = None,
        sentiment: TicketSentiment | None = None,
        sentiment_confidence: TicketSignalConfidence | None = None,
        sentiment_reason: str | None = None,
    ) -> None:
        recent_messages = list(repository.recent_messages_by_ticket_id.get(ticket_id, ()))
        recent_messages.append(
            TicketMessageDetails(
                telegram_message_id=telegram_message_id,
                sender_type=sender_type,
                sender_operator_id=sender_operator_id,
                sender_operator_name=None,
                text=text,
                attachment=attachment,
                sentiment=sentiment,
                sentiment_confidence=sentiment_confidence,
                sentiment_reason=sentiment_reason,
                created_at=datetime.now(UTC),
            )
        )
        repository.recent_messages_by_ticket_id[ticket_id] = tuple(recent_messages[-6:])
        repository.added_messages.append(
            {
                "ticket_id": ticket_id,
                "telegram_message_id": telegram_message_id,
                "sender_type": sender_type,
                "text": text,
                "attachment": attachment,
                "sender_operator_id": sender_operator_id,
                "sentiment": sentiment,
                "sentiment_confidence": sentiment_confidence,
                "sentiment_reason": sentiment_reason,
            }
        )

    async def list_recent_for_ticket(
        *,
        ticket_id: int,
        limit: int = 6,
    ) -> tuple[TicketMessageDetails, ...]:
        del limit
        return tuple(repository.recent_messages_by_ticket_id.get(ticket_id, ()))

    async def mark_duplicate(
        *,
        ticket_id: int,
        telegram_message_id: int,
        occurred_at: datetime,
    ) -> None:
        repository.duplicate_marks.append(
            {
                "ticket_id": ticket_id,
                "telegram_message_id": telegram_message_id,
                "occurred_at": occurred_at,
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
    repository.list_recent_for_ticket = AsyncMock(side_effect=list_recent_for_ticket)
    repository.mark_duplicate = AsyncMock(side_effect=mark_duplicate)
    repository.allocate_internal_telegram_message_id = AsyncMock(
        side_effect=allocate_internal_telegram_message_id
    )
    return repository


def build_internal_note_repository_mock() -> Mock:
    repository = Mock()
    repository.added_notes = []

    async def add(
        *,
        ticket_id: int,
        author_operator_id: int,
        text: str,
    ) -> SimpleNamespace:
        note = SimpleNamespace(
            id=len(repository.added_notes) + 1,
            ticket_id=ticket_id,
            author_operator_id=author_operator_id,
            author_operator_name=None,
            text=text,
            created_at=datetime.now(UTC),
        )
        repository.added_notes.append(
            {
                "ticket_id": ticket_id,
                "author_operator_id": author_operator_id,
                "text": text,
            }
        )
        return note

    repository.add = AsyncMock(side_effect=add)
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


def build_audit_repository_mock() -> Mock:
    repository = Mock()
    repository.entries = []

    async def add(**kwargs: object) -> None:
        repository.entries.append(dict(kwargs))

    repository.add = AsyncMock(side_effect=add)
    return repository


def build_ticket_ai_summary_repository_mock() -> Mock:
    repository = Mock()
    repository.get_by_ticket_id = AsyncMock(return_value=None)
    repository.upsert = AsyncMock()
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


@dataclass
class StubOperatorInviteRepository:
    def __post_init__(self) -> None:
        self.records_by_hash: dict[str, SimpleNamespace] = {}
        self.next_id = 1

    async def create(
        self,
        *,
        code_hash: str,
        created_by_telegram_user_id: int,
        expires_at: datetime,
        max_uses: int = 1,
    ) -> SimpleNamespace:
        record = SimpleNamespace(
            id=self.next_id,
            code_hash=code_hash,
            created_by_telegram_user_id=created_by_telegram_user_id,
            expires_at=expires_at,
            max_uses=max_uses,
            used_count=0,
            is_active=True,
            last_used_at=None,
            last_used_telegram_user_id=None,
            deactivated_at=None,
        )
        self.records_by_hash[code_hash] = record
        self.next_id += 1
        return record

    async def get_by_code_hash(self, *, code_hash: str) -> SimpleNamespace | None:
        return self.records_by_hash.get(code_hash)

    async def mark_used(
        self,
        *,
        invite_id: int,
        telegram_user_id: int,
        used_at: datetime,
    ) -> SimpleNamespace | None:
        record = next(
            (item for item in self.records_by_hash.values() if item.id == invite_id),
            None,
        )
        if record is None:
            return None
        record.used_count += 1
        record.last_used_at = used_at
        record.last_used_telegram_user_id = telegram_user_id
        if record.used_count >= record.max_uses:
            record.is_active = False
            record.deactivated_at = used_at
        return record


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
    ticket_ai_summary_repository: Any | None = None,
    message_repository: Any | None = None,
    internal_note_repository: Any | None = None,
    event_repository: Any | None = None,
    operator_repository: Any | None = None,
    operator_invite_repository: Any | None = None,
    macro_repository: Any | None = None,
    sla_policy_repository: Any | None = None,
    tag_repository: StubTagRepository | None = None,
    ticket_category_repository: StubTicketCategoryRepository | None = None,
    ticket_tag_repository: StubTicketTagRepository | None = None,
    super_admin_telegram_user_ids: frozenset[int] | None = None,
    ai_client_factory: AIServiceClientFactory | None = None,
) -> HelpdeskService:
    active_tag_repository = tag_repository or StubTagRepository()
    return HelpdeskService(
        ticket_repository=ticket_repository,
        ticket_analytics_repository=ticket_repository,
        ticket_feedback_repository=ticket_feedback_repository or StubTicketFeedbackRepository(),
        ticket_ai_summary_repository=(
            ticket_ai_summary_repository or build_ticket_ai_summary_repository_mock()
        ),
        ticket_message_repository=message_repository or build_message_repository_mock(),
        ticket_internal_note_repository=(
            internal_note_repository or build_internal_note_repository_mock()
        ),
        ticket_event_repository=event_repository or build_event_repository_mock(),
        audit_log_repository=build_audit_repository_mock(),
        operator_repository=operator_repository or build_operator_repository_mock({}),
        operator_invite_repository=operator_invite_repository or StubOperatorInviteRepository(),
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
        ai_client_factory=ai_client_factory or build_ai_client_factory(),
        export_renderers=HelpdeskExportRenderers(
            ticket_report_csv=render_ticket_report_csv,
            ticket_report_html=render_ticket_report_html,
            analytics_snapshot_csv=render_analytics_snapshot_csv,
            analytics_snapshot_html=render_analytics_snapshot_html,
        ),
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
        ClientTicketMessageCommand(
            client_chat_id=555,
            telegram_message_id=777,
            text="Cannot log in",
        )
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


async def test_create_ticket_from_first_media_message_builds_attachment_aware_subject() -> None:
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
        ClientTicketMessageCommand(
            client_chat_id=555,
            telegram_message_id=777,
            text=None,
            attachment=TicketAttachmentDetails(
                kind=TicketAttachmentKind.PHOTO,
                telegram_file_id="photo-1",
                telegram_file_unique_id="photo-unique-1",
                filename=None,
                mime_type="image/jpeg",
                storage_path="photo/photo-unique-1.jpg",
            ),
        )
    )

    assert result.public_id == public_id
    assert ticket_repository.create_calls[0]["subject"] == "Фото"
    assert message_repository.added_messages[0]["attachment"] is not None
    assert message_repository.added_messages[0]["text"] is None


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
        ClientTicketMessageCommand(
            client_chat_id=active_ticket.client_chat_id,
            telegram_message_id=888,
            text="Any update?",
        )
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


async def test_follow_up_client_message_flags_sentiment_and_raises_priority() -> None:
    public_id = uuid4()
    active_ticket = build_ticket(
        ticket_id=2,
        public_id=public_id,
        status=TicketStatus.ASSIGNED,
        priority=TicketPriority.NORMAL,
    )
    ticket_repository = StubTicketRepository(
        created_ticket=build_ticket(ticket_id=1, public_id=uuid4(), status=TicketStatus.NEW),
        active_ticket=active_ticket,
    )
    message_repository = build_message_repository_mock()
    event_repository = build_event_repository_mock()
    ai_client = StubSentimentAIClient(
        AnalyzedTicketSentimentResult(
            available=True,
            sentiment=TicketSentiment.ESCALATION_RISK,
            confidence=TicketSignalConfidence.HIGH,
            reason="Резкие формулировки и требование немедленного ответа.",
        )
    )
    service = build_service(
        ticket_repository=ticket_repository,
        message_repository=message_repository,
        event_repository=event_repository,
        ai_client_factory=build_ai_client_factory(ai_client),
    )

    result = await service.create_ticket_from_client_message(
        ClientTicketMessageCommand(
            client_chat_id=active_ticket.client_chat_id,
            telegram_message_id=889,
            text="Это уже безобразие, сколько можно, ответьте немедленно!",
        )
    )

    assert result.event_type == TicketEventType.CLIENT_MESSAGE_ADDED
    assert active_ticket.priority == TicketPriority.HIGH
    assert active_ticket.sentiment == TicketSentiment.ESCALATION_RISK
    assert message_repository.added_messages[0]["sentiment"] == TicketSentiment.ESCALATION_RISK
    assert [event["event_type"] for event in event_repository.added_events] == [
        TicketEventType.CLIENT_MESSAGE_ADDED,
        TicketEventType.CLIENT_SENTIMENT_FLAGGED,
    ]
    assert ai_client.commands[0].text == "Это уже безобразие, сколько можно, ответьте немедленно!"


async def test_follow_up_client_duplicate_burst_is_collapsed_without_new_message_row() -> None:
    public_id = uuid4()
    canonical_message = TicketMessageDetails(
        telegram_message_id=501,
        sender_type=TicketMessageSenderType.CLIENT,
        sender_operator_id=None,
        sender_operator_name=None,
        text="????",
        created_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    active_ticket = build_ticket(
        ticket_id=2,
        public_id=public_id,
        status=TicketStatus.ASSIGNED,
        last_message_text="????",
        last_message_sender_type=TicketMessageSenderType.CLIENT,
        message_history=(canonical_message,),
    )
    ticket_repository = StubTicketRepository(
        created_ticket=build_ticket(ticket_id=1, public_id=uuid4(), status=TicketStatus.NEW),
        active_ticket=active_ticket,
    )
    message_repository = build_message_repository_mock()
    message_repository.recent_messages_by_ticket_id[active_ticket.id] = (canonical_message,)
    event_repository = build_event_repository_mock()
    service = build_service(
        ticket_repository=ticket_repository,
        message_repository=message_repository,
        event_repository=event_repository,
    )

    result = await service.create_ticket_from_client_message(
        ClientTicketMessageCommand(
            client_chat_id=active_ticket.client_chat_id,
            telegram_message_id=890,
            text="????????",
        )
    )

    assert result.event_type == TicketEventType.CLIENT_MESSAGE_DUPLICATE_COLLAPSED
    assert message_repository.added_messages == []
    assert message_repository.duplicate_marks[0]["telegram_message_id"] == 501
    assert [event["event_type"] for event in event_repository.added_events] == [
        TicketEventType.CLIENT_MESSAGE_DUPLICATE_COLLAPSED,
    ]


async def test_create_ticket_from_client_intake_persists_selected_category() -> None:
    public_id = uuid4()
    created_ticket = build_ticket(ticket_id=1, public_id=public_id, status=TicketStatus.NEW)
    ticket_repository = StubTicketRepository(created_ticket=created_ticket)
    service = build_service(ticket_repository=ticket_repository)

    result = await service.create_ticket_from_client_intake(
        ClientTicketMessageCommand(
            client_chat_id=555,
            telegram_message_id=777,
            category_id=2,
            text="Нужна помощь с другим вопросом",
        )
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
        TicketAssignmentCommand(
            ticket_public_id=public_id,
            operator=OperatorIdentity(
                telegram_user_id=1001,
                display_name="Operator One",
            ),
        )
    )
    second_result = await service.assign_ticket_to_operator(
        TicketAssignmentCommand(
            ticket_public_id=public_id,
            operator=OperatorIdentity(
                telegram_user_id=1002,
                display_name="Operator Two",
            ),
        )
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
        await service.list_operators(actor=RequestActor(telegram_user_id=1001))
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
        OperatorIdentity(
            telegram_user_id=3001,
            display_name="Новый оператор",
        )
    )

    assert result.changed is True
    assert result.operator.telegram_user_id == 3001
    assert 3001 in operator_repository.active_operator_ids


async def test_create_operator_invite_returns_one_time_code() -> None:
    invite_repository = StubOperatorInviteRepository()
    service = build_service(
        ticket_repository=StubTicketRepository(
            created_ticket=build_ticket(ticket_id=1, public_id=uuid4(), status=TicketStatus.NEW)
        ),
        operator_invite_repository=invite_repository,
    )

    result = await service.create_operator_invite(actor=RequestActor(telegram_user_id=42))

    assert result.code.startswith(OPERATOR_INVITE_PREFIX)
    stored = next(iter(invite_repository.records_by_hash.values()))
    assert stored.max_uses == 1
    assert stored.is_active is True


async def test_redeem_operator_invite_promotes_user_and_deactivates_code() -> None:
    operator_repository = StubOperatorManagementRepository()
    invite_repository = StubOperatorInviteRepository()
    service = build_service(
        ticket_repository=StubTicketRepository(
            created_ticket=build_ticket(ticket_id=1, public_id=uuid4(), status=TicketStatus.NEW)
        ),
        operator_repository=operator_repository,
        operator_invite_repository=invite_repository,
    )

    invite = await service.create_operator_invite(actor=RequestActor(telegram_user_id=42))
    preview = await service.preview_operator_invite(code=invite.code)
    result = await service.redeem_operator_invite(
        code=invite.code,
        operator=OperatorIdentity(
            telegram_user_id=3001,
            display_name="Анна Смирнова",
            username="anna_smirnova",
        ),
    )

    assert preview.remaining_uses == 1
    assert result.operator.operator.telegram_user_id == 3001
    assert 3001 in operator_repository.active_operator_ids
    stored = next(iter(invite_repository.records_by_hash.values()))
    assert stored.used_count == 1
    assert stored.is_active is False


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
        AssignNextQueuedTicketCommand(
            operator=OperatorIdentity(
                telegram_user_id=1001,
                display_name="Operator One",
            )
        )
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
            AssignNextQueuedTicketCommand(
                operator=OperatorIdentity(
                    telegram_user_id=2002,
                    display_name="Regular User",
                )
            ),
            actor=RequestActor(telegram_user_id=2002),
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


async def test_get_analytics_snapshot_returns_richer_operational_view() -> None:
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
        created_tickets_count=9,
        closed_tickets_count=5,
        feedback_submissions_count=4,
        average_feedback_rating=4.7,
        feedback_rating_distribution=[
            SimpleNamespace(rating=5, count=3),
            SimpleNamespace(rating=4, count=1),
        ],
        operator_closure_stats=[
            SimpleNamespace(
                operator_id=7,
                display_name="Operator One",
                closed_ticket_count=4,
                average_first_response_time_seconds=120.0,
                average_resolution_time_seconds=5400.0,
                average_satisfaction=4.8,
                feedback_count=3,
            ),
            SimpleNamespace(
                operator_id=9,
                display_name="Operator Two",
                closed_ticket_count=1,
                average_first_response_time_seconds=240.0,
                average_resolution_time_seconds=9000.0,
                average_satisfaction=4.0,
                feedback_count=1,
            ),
        ],
        created_ticket_category_counts=[
            SimpleNamespace(category_id=1, category_title="Доступ и вход", ticket_count=5),
            SimpleNamespace(category_id=2, category_title="Платежи", ticket_count=3),
        ],
        open_ticket_category_counts=[
            SimpleNamespace(category_id=1, category_title="Доступ и вход", ticket_count=2),
            SimpleNamespace(category_id=2, category_title="Платежи", ticket_count=1),
        ],
        closed_ticket_category_counts=[
            SimpleNamespace(category_id=1, category_title="Доступ и вход", ticket_count=3),
            SimpleNamespace(category_id=2, category_title="Платежи", ticket_count=2),
        ],
        category_feedback_stats=[
            SimpleNamespace(
                category_id=1,
                category_title="Доступ и вход",
                average_satisfaction=4.5,
                feedback_count=2,
            ),
            SimpleNamespace(
                category_id=2,
                category_title="Платежи",
                average_satisfaction=5.0,
                feedback_count=2,
            ),
        ],
        sla_breach_counts={
            "sla_breached_first_response": 2,
            "sla_breached_resolution": 1,
        },
        sla_breach_category_counts=[
            SimpleNamespace(category_id=1, category_title="Доступ и вход", breach_count=2),
        ],
    )
    service = build_service(ticket_repository=ticket_repository)

    snapshot = await service.get_analytics_snapshot(window=AnalyticsWindow.DAYS_7)

    assert snapshot.total_open_tickets == 6
    assert snapshot.period_created_tickets_count == 9
    assert snapshot.period_closed_tickets_count == 5
    assert snapshot.feedback_count == 4
    assert snapshot.feedback_coverage_percent == 80
    assert snapshot.satisfaction_average == 4.7
    assert snapshot.best_operators_by_closures[0].display_name == "Operator One"
    assert snapshot.best_operators_by_satisfaction[0].display_name == "Operator One"
    assert snapshot.top_categories[0].category_title == "Доступ и вход"
    assert snapshot.first_response_breach_count == 2
    assert snapshot.resolution_breach_count == 1


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
        ClientTicketMessageCommand(
            client_chat_id=555,
            telegram_message_id=7001,
            text="Cannot log in",
        )
    )
    taken = await service.assign_next_ticket_to_operator(
        AssignNextQueuedTicketCommand(
            operator=OperatorIdentity(
                telegram_user_id=1001,
                display_name="Operator One",
            )
        )
    )
    reply = await service.reply_to_ticket_as_operator(
        OperatorTicketReplyCommand(
            ticket_public_id=public_id,
            operator=OperatorIdentity(
                telegram_user_id=1001,
                display_name="Operator One",
                username="operator_one",
            ),
            telegram_message_id=7002,
            text="Please try again now.",
        )
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
            OperatorTicketReplyCommand(
                ticket_public_id=public_id,
                operator=OperatorIdentity(
                    telegram_user_id=1001,
                    display_name="Operator One",
                    username="operator_one",
                ),
                telegram_message_id=4321,
                text="Please try again now.",
            )
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
        actor=RequestActor(telegram_user_id=1001),
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
        actor=RequestActor(telegram_user_id=1001),
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
        OperatorTicketReplyCommand(
            ticket_public_id=public_id,
            operator=OperatorIdentity(
                telegram_user_id=1001,
                display_name="Operator One",
                username="operator_one",
            ),
            telegram_message_id=4321,
            text="Please try again now.",
        )
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
        ApplyMacroToTicketCommand(
            ticket_public_id=public_id,
            macro_id=5,
            operator=OperatorIdentity(
                telegram_user_id=1001,
                display_name="Operator One",
                username="operator_one",
            ),
        )
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
        actor=RequestActor(telegram_user_id=42),
    )
    updated_title = await service.update_macro_title(
        macro_id=created.id,
        title="Финальный ответ",
        actor=RequestActor(telegram_user_id=42),
    )
    updated_body = await service.update_macro_body(
        macro_id=created.id,
        body="Проверили. Всё исправлено.",
        actor=RequestActor(telegram_user_id=42),
    )
    deleted = await service.delete_macro(
        macro_id=created.id,
        actor=RequestActor(telegram_user_id=42),
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
            actor=RequestActor(telegram_user_id=42),
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
