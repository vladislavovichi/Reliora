from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID

from domain.contracts.repositories import (
    MacroRepository,
    OperatorRepository,
    SLAPolicyRecord,
    SLAPolicyRepository,
    TagRepository,
    TicketEventRepository,
    TicketMessageRepository,
    TicketRepository,
    TicketTagRepository,
)
from domain.entities.ticket import Ticket
from domain.entities.ticket import TicketDetails as DomainTicketDetails
from domain.enums.tickets import TicketEventType, TicketMessageSenderType, TicketStatus
from domain.tickets import (
    InvalidTicketTransitionError,
    ensure_assignable,
    ensure_closable,
    ensure_escalatable,
    ensure_message_addable,
    ensure_operator_replyable,
)


def utcnow() -> datetime:
    return datetime.now(UTC)


def build_ticket_subject(message_text: str) -> str:
    first_line = (
        message_text.strip().splitlines()[0]
        if message_text.strip()
        else "Обращение клиента"
    )
    return first_line[:255]


def format_public_ticket_number(public_id: UUID) -> str:
    return f"HD-{public_id.hex[:8].upper()}"


def build_ticket_summary(
    ticket: Ticket,
    *,
    created: bool = False,
    event_type: TicketEventType | None = None,
) -> TicketSummary:
    return TicketSummary(
        public_id=ticket.public_id,
        public_number=format_public_ticket_number(ticket.public_id),
        status=ticket.status,
        created=created,
        event_type=event_type,
    )


def build_status_payload(
    *,
    from_status: TicketStatus,
    to_status: TicketStatus,
    assigned_operator_id: int | None,
    previous_operator_id: int | None = None,
    actor_operator_id: int | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "from_status": from_status.value,
        "to_status": to_status.value,
    }
    if assigned_operator_id is not None:
        payload["assigned_operator_id"] = assigned_operator_id
    if previous_operator_id is not None:
        payload["previous_operator_id"] = previous_operator_id
    if actor_operator_id is not None:
        payload["actor_operator_id"] = actor_operator_id
    return payload


def build_message_payload(
    *,
    telegram_message_id: int,
    sender_type: TicketMessageSenderType,
    sender_operator_id: int | None,
    extra_payload: Mapping[str, object] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "telegram_message_id": telegram_message_id,
        "sender_type": sender_type.value,
    }
    if sender_operator_id is not None:
        payload["sender_operator_id"] = sender_operator_id
    if extra_payload is not None:
        payload.update(extra_payload)
    return payload


def build_event_type_for_message(
    sender_type: TicketMessageSenderType,
) -> TicketEventType | None:
    if sender_type == TicketMessageSenderType.CLIENT:
        return TicketEventType.CLIENT_MESSAGE_ADDED
    if sender_type == TicketMessageSenderType.OPERATOR:
        return TicketEventType.OPERATOR_MESSAGE_ADDED
    return None


@dataclass(slots=True)
class TicketSummary:
    public_id: UUID
    public_number: str
    status: TicketStatus
    created: bool = False
    event_type: TicketEventType | None = None


@dataclass(slots=True)
class TicketStats:
    total: int
    open_total: int
    by_status: dict[TicketStatus, int]


@dataclass(slots=True)
class QueuedTicketSummary:
    public_id: UUID
    public_number: str
    subject: str
    priority: str
    status: TicketStatus


def build_queued_ticket_summary(ticket: Ticket) -> QueuedTicketSummary:
    return QueuedTicketSummary(
        public_id=ticket.public_id,
        public_number=format_public_ticket_number(ticket.public_id),
        subject=ticket.subject,
        priority=ticket.priority.value,
        status=ticket.status,
    )


@dataclass(slots=True)
class TicketDetailsSummary:
    public_id: UUID
    public_number: str
    client_chat_id: int
    status: TicketStatus
    priority: str
    subject: str
    assigned_operator_id: int | None
    assigned_operator_name: str | None
    tags: tuple[str, ...]
    last_message_text: str | None
    last_message_sender_type: TicketMessageSenderType | None


def build_ticket_details_summary(ticket: DomainTicketDetails) -> TicketDetailsSummary:
    return TicketDetailsSummary(
        public_id=ticket.public_id,
        public_number=format_public_ticket_number(ticket.public_id),
        client_chat_id=ticket.client_chat_id,
        status=ticket.status,
        priority=ticket.priority.value,
        subject=ticket.subject,
        assigned_operator_id=ticket.assigned_operator_id,
        assigned_operator_name=ticket.assigned_operator_name,
        tags=ticket.tags,
        last_message_text=ticket.last_message_text,
        last_message_sender_type=ticket.last_message_sender_type,
    )


@dataclass(slots=True)
class OperatorReplyResult:
    ticket: TicketSummary
    client_chat_id: int


@dataclass(slots=True)
class MacroSummary:
    id: int
    title: str
    body: str


@dataclass(slots=True)
class MacroApplicationResult:
    ticket: TicketSummary
    client_chat_id: int
    macro: MacroSummary


@dataclass(slots=True)
class TicketTagsSummary:
    public_id: UUID
    public_number: str
    tags: tuple[str, ...]


@dataclass(slots=True)
class TicketTagMutationResult:
    ticket: TicketSummary
    tag: str
    changed: bool
    tags: tuple[str, ...]


class SLADeadlineStatus(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    OK = "ok"
    APPROACHING = "approaching"
    BREACHED = "breached"


@dataclass(slots=True)
class SLADeadlineSummary:
    deadline_at: datetime | None
    status: SLADeadlineStatus
    remaining_seconds: int | None


@dataclass(slots=True)
class TicketSLAEvaluationSummary:
    public_id: UUID
    public_number: str
    status: TicketStatus
    assigned_operator_id: int | None
    policy_name: str | None
    first_response: SLADeadlineSummary
    resolution: SLADeadlineSummary
    stale_assignment: SLADeadlineSummary
    should_auto_escalate: bool
    should_auto_reassign: bool


@dataclass(slots=True, frozen=True)
class SLAAutoReassignmentTarget:
    ticket_public_id: UUID
    telegram_user_id: int
    display_name: str
    username: str | None = None


@dataclass(slots=True)
class TicketSLAProcessingSummary:
    evaluation: TicketSLAEvaluationSummary
    persisted_event_types: tuple[TicketEventType, ...]


@dataclass(slots=True)
class SLABatchProcessingResult:
    processed_tickets: tuple[TicketSLAProcessingSummary, ...]
    evaluated_count: int
    auto_escalated_count: int
    auto_reassigned_count: int


def build_sla_approaching_window(*, total_minutes: int) -> timedelta:
    approaching_minutes = max(5, min(30, (total_minutes + 4) // 5))
    return timedelta(minutes=approaching_minutes)


def build_stale_assignment_window(policy: SLAPolicyRecord) -> timedelta:
    stale_minutes = min(
        policy.resolution_minutes,
        max(
            policy.first_response_minutes,
            max(15, policy.resolution_minutes // 4),
        ),
    )
    return timedelta(minutes=stale_minutes)


def evaluate_deadline(
    *,
    deadline_at: datetime | None,
    now: datetime,
    approaching_window: timedelta | None = None,
) -> SLADeadlineSummary:
    if deadline_at is None:
        return SLADeadlineSummary(
            deadline_at=None,
            status=SLADeadlineStatus.NOT_APPLICABLE,
            remaining_seconds=None,
        )

    remaining_seconds = int((deadline_at - now).total_seconds())
    if remaining_seconds <= 0:
        return SLADeadlineSummary(
            deadline_at=deadline_at,
            status=SLADeadlineStatus.BREACHED,
            remaining_seconds=remaining_seconds,
        )

    if (
        approaching_window is not None
        and remaining_seconds <= int(approaching_window.total_seconds())
    ):
        status = SLADeadlineStatus.APPROACHING
    else:
        status = SLADeadlineStatus.OK

    return SLADeadlineSummary(
        deadline_at=deadline_at,
        status=status,
        remaining_seconds=remaining_seconds,
    )


def build_sla_event_payload(
    *,
    policy: SLAPolicyRecord,
    deadline_at: datetime | None,
    checked_at: datetime,
    remaining_seconds: int | None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "policy_name": policy.name,
        "checked_at": checked_at.isoformat(),
    }
    if deadline_at is not None:
        payload["deadline_at"] = deadline_at.isoformat()
    if remaining_seconds is not None:
        payload["remaining_seconds"] = remaining_seconds
    return payload


def evaluate_ticket_sla(
    *,
    ticket: Ticket,
    policy: SLAPolicyRecord | None,
    now: datetime,
) -> TicketSLAEvaluationSummary:
    if policy is None:
        not_applicable = SLADeadlineSummary(
            deadline_at=None,
            status=SLADeadlineStatus.NOT_APPLICABLE,
            remaining_seconds=None,
        )
        return TicketSLAEvaluationSummary(
            public_id=ticket.public_id,
            public_number=format_public_ticket_number(ticket.public_id),
            status=ticket.status,
            assigned_operator_id=ticket.assigned_operator_id,
            policy_name=None,
            first_response=not_applicable,
            resolution=not_applicable,
            stale_assignment=not_applicable,
            should_auto_escalate=False,
            should_auto_reassign=False,
        )

    first_response_deadline_at: datetime | None = None
    if ticket.closed_at is None and ticket.first_response_at is None:
        first_response_deadline_at = ticket.created_at + timedelta(
            minutes=policy.first_response_minutes
        )

    resolution_deadline_at: datetime | None = None
    if ticket.closed_at is None:
        resolution_deadline_at = ticket.created_at + timedelta(
            minutes=policy.resolution_minutes
        )

    stale_assignment_deadline_at: datetime | None = None
    if (
        ticket.status == TicketStatus.ASSIGNED
        and ticket.assigned_operator_id is not None
        and ticket.closed_at is None
    ):
        stale_assignment_deadline_at = ticket.updated_at + build_stale_assignment_window(
            policy
        )

    first_response = evaluate_deadline(
        deadline_at=first_response_deadline_at,
        now=now,
        approaching_window=build_sla_approaching_window(
            total_minutes=policy.first_response_minutes
        ),
    )
    resolution = evaluate_deadline(
        deadline_at=resolution_deadline_at,
        now=now,
        approaching_window=build_sla_approaching_window(
            total_minutes=policy.resolution_minutes
        ),
    )
    stale_assignment = evaluate_deadline(
        deadline_at=stale_assignment_deadline_at,
        now=now,
    )

    should_auto_escalate = (
        ticket.status in {TicketStatus.QUEUED, TicketStatus.ASSIGNED}
        and (
            first_response.status == SLADeadlineStatus.BREACHED
            or resolution.status == SLADeadlineStatus.BREACHED
        )
    )
    should_auto_reassign = (
        ticket.status == TicketStatus.ASSIGNED
        and ticket.assigned_operator_id is not None
        and stale_assignment.status == SLADeadlineStatus.BREACHED
        and not should_auto_escalate
    )

    return TicketSLAEvaluationSummary(
        public_id=ticket.public_id,
        public_number=format_public_ticket_number(ticket.public_id),
        status=ticket.status,
        assigned_operator_id=ticket.assigned_operator_id,
        policy_name=policy.name,
        first_response=first_response,
        resolution=resolution,
        stale_assignment=stale_assignment,
        should_auto_escalate=should_auto_escalate,
        should_auto_reassign=should_auto_reassign,
    )


class CreateTicketFromClientMessageUseCase:
    def __init__(
        self,
        ticket_repository: TicketRepository,
        ticket_message_repository: TicketMessageRepository,
        ticket_event_repository: TicketEventRepository,
    ) -> None:
        self.ticket_repository = ticket_repository
        self.ticket_message_repository = ticket_message_repository
        self.ticket_event_repository = ticket_event_repository

    async def __call__(
        self,
        *,
        client_chat_id: int,
        telegram_message_id: int,
        text: str,
    ) -> TicketSummary:
        active_ticket = await self.ticket_repository.get_active_by_client_chat_id(
            client_chat_id
        )
        if active_ticket is not None:
            if active_ticket.id is None:
                raise RuntimeError("Не найден идентификатор активной заявки.")

            ensure_message_addable(active_ticket.status)
            await self.ticket_message_repository.add(
                ticket_id=active_ticket.id,
                telegram_message_id=telegram_message_id,
                sender_type=TicketMessageSenderType.CLIENT,
                text=text,
            )
            await self.ticket_event_repository.add(
                ticket_id=active_ticket.id,
                event_type=TicketEventType.CLIENT_MESSAGE_ADDED,
                payload_json=build_message_payload(
                    telegram_message_id=telegram_message_id,
                    sender_type=TicketMessageSenderType.CLIENT,
                    sender_operator_id=None,
                ),
            )
            return build_ticket_summary(
                active_ticket,
                created=False,
                event_type=TicketEventType.CLIENT_MESSAGE_ADDED,
            )

        ticket = await self.ticket_repository.create(
            client_chat_id=client_chat_id,
            subject=build_ticket_subject(text),
        )
        if ticket.id is None:
            raise RuntimeError("Не удалось сгенерировать идентификатор заявки.")

        await self.ticket_event_repository.add(
            ticket_id=ticket.id,
            event_type=TicketEventType.CREATED,
            payload_json={
                "status": ticket.status.value,
                "subject": ticket.subject,
                "client_chat_id": ticket.client_chat_id,
            },
        )

        queued_ticket = await self.ticket_repository.enqueue(
            ticket_public_id=ticket.public_id
        )
        if queued_ticket is None:
            raise RuntimeError("Не удалось поставить заявку в очередь.")

        await self.ticket_event_repository.add(
            ticket_id=ticket.id,
            event_type=TicketEventType.QUEUED,
            payload_json=build_status_payload(
                from_status=TicketStatus.NEW,
                to_status=queued_ticket.status,
                assigned_operator_id=queued_ticket.assigned_operator_id,
            ),
        )

        await self.ticket_message_repository.add(
            ticket_id=ticket.id,
            telegram_message_id=telegram_message_id,
            sender_type=TicketMessageSenderType.CLIENT,
            text=text,
        )
        await self.ticket_event_repository.add(
            ticket_id=ticket.id,
            event_type=TicketEventType.CLIENT_MESSAGE_ADDED,
            payload_json=build_message_payload(
                telegram_message_id=telegram_message_id,
                sender_type=TicketMessageSenderType.CLIENT,
                sender_operator_id=None,
            ),
        )

        return build_ticket_summary(
            queued_ticket,
            created=True,
            event_type=TicketEventType.QUEUED,
        )


class AddMessageToTicketUseCase:
    def __init__(
        self,
        ticket_repository: TicketRepository,
        ticket_message_repository: TicketMessageRepository,
        ticket_event_repository: TicketEventRepository,
    ) -> None:
        self.ticket_repository = ticket_repository
        self.ticket_message_repository = ticket_message_repository
        self.ticket_event_repository = ticket_event_repository

    async def __call__(
        self,
        *,
        ticket_public_id: UUID,
        telegram_message_id: int,
        sender_type: TicketMessageSenderType,
        text: str,
        sender_operator_id: int | None = None,
        extra_event_payload: Mapping[str, object] | None = None,
    ) -> TicketSummary | None:
        ticket = await self.ticket_repository.get_by_public_id(ticket_public_id)
        if ticket is None or ticket.id is None:
            return None

        ensure_message_addable(ticket.status)
        current_time = utcnow()
        if (
            sender_type == TicketMessageSenderType.OPERATOR
            and ticket.first_response_at is None
        ):
            ticket.first_response_at = current_time
        ticket.updated_at = current_time

        await self.ticket_message_repository.add(
            ticket_id=ticket.id,
            telegram_message_id=telegram_message_id,
            sender_type=sender_type,
            text=text,
            sender_operator_id=sender_operator_id,
        )

        event_type = build_event_type_for_message(sender_type)
        if event_type is not None:
            await self.ticket_event_repository.add(
                ticket_id=ticket.id,
                event_type=event_type,
                payload_json=build_message_payload(
                    telegram_message_id=telegram_message_id,
                    sender_type=sender_type,
                    sender_operator_id=sender_operator_id,
                    extra_payload=extra_event_payload,
                ),
            )

        return build_ticket_summary(ticket, event_type=event_type)


class AssignTicketToOperatorUseCase:
    def __init__(
        self,
        ticket_repository: TicketRepository,
        ticket_event_repository: TicketEventRepository,
        operator_repository: OperatorRepository,
    ) -> None:
        self.ticket_repository = ticket_repository
        self.ticket_event_repository = ticket_event_repository
        self.operator_repository = operator_repository

    async def __call__(
        self,
        *,
        ticket_public_id: UUID,
        telegram_user_id: int,
        display_name: str,
        username: str | None = None,
    ) -> TicketSummary | None:
        ticket = await self.ticket_repository.get_by_public_id(ticket_public_id)
        if ticket is None or ticket.id is None:
            return None

        ensure_assignable(ticket.status)
        operator_id = await self.operator_repository.get_or_create(
            telegram_user_id=telegram_user_id,
            display_name=display_name,
            username=username,
        )

        previous_status = ticket.status
        previous_operator_id = ticket.assigned_operator_id
        if (
            previous_status == TicketStatus.ASSIGNED
            and previous_operator_id == operator_id
        ):
            raise InvalidTicketTransitionError("Заявка уже назначена этому оператору.")

        event_type = TicketEventType.ASSIGNED
        if previous_operator_id is not None and previous_operator_id != operator_id:
            event_type = TicketEventType.REASSIGNED

        assigned_ticket = await self.ticket_repository.assign_to_operator(
            ticket_public_id=ticket_public_id,
            operator_id=operator_id,
        )
        if assigned_ticket is None:
            return None

        await self.ticket_event_repository.add(
            ticket_id=ticket.id,
            event_type=event_type,
            payload_json=build_status_payload(
                from_status=previous_status,
                to_status=assigned_ticket.status,
                assigned_operator_id=operator_id,
                previous_operator_id=previous_operator_id,
                actor_operator_id=operator_id,
            ),
        )

        return build_ticket_summary(assigned_ticket, event_type=event_type)


class GetNextQueuedTicketUseCase:
    def __init__(self, ticket_repository: TicketRepository) -> None:
        self.ticket_repository = ticket_repository

    async def __call__(
        self, *, prioritize_priority: bool = False
    ) -> QueuedTicketSummary | None:
        ticket = await self.ticket_repository.get_next_queued_ticket(
            prioritize_priority=prioritize_priority
        )
        if ticket is None:
            return None

        return build_queued_ticket_summary(ticket)


class ListQueuedTicketsUseCase:
    def __init__(self, ticket_repository: TicketRepository) -> None:
        self.ticket_repository = ticket_repository

    async def __call__(
        self,
        *,
        limit: int | None = None,
        prioritize_priority: bool = False,
    ) -> Sequence[QueuedTicketSummary]:
        tickets = await self.ticket_repository.list_queued_tickets(
            limit=limit,
            prioritize_priority=prioritize_priority,
        )
        return [build_queued_ticket_summary(ticket) for ticket in tickets]


class GetTicketDetailsUseCase:
    def __init__(self, ticket_repository: TicketRepository) -> None:
        self.ticket_repository = ticket_repository

    async def __call__(self, *, ticket_public_id: UUID) -> TicketDetailsSummary | None:
        ticket = await self.ticket_repository.get_details_by_public_id(ticket_public_id)
        if ticket is None:
            return None

        return build_ticket_details_summary(ticket)


class AssignNextQueuedTicketUseCase:
    def __init__(
        self,
        ticket_repository: TicketRepository,
        ticket_event_repository: TicketEventRepository,
        operator_repository: OperatorRepository,
    ) -> None:
        self.ticket_repository = ticket_repository
        self.ticket_event_repository = ticket_event_repository
        self.operator_repository = operator_repository

    async def __call__(
        self,
        *,
        telegram_user_id: int,
        display_name: str,
        username: str | None = None,
        prioritize_priority: bool = False,
    ) -> TicketSummary | None:
        operator_id = await self.operator_repository.get_or_create(
            telegram_user_id=telegram_user_id,
            display_name=display_name,
            username=username,
        )

        for _ in range(3):
            ticket = await self.ticket_repository.get_next_queued_ticket(
                prioritize_priority=prioritize_priority
            )
            if ticket is None or ticket.id is None:
                return None

            assigned_ticket = await self.ticket_repository.assign_queued_to_operator(
                ticket_public_id=ticket.public_id,
                operator_id=operator_id,
            )
            if assigned_ticket is None:
                continue

            await self.ticket_event_repository.add(
                ticket_id=ticket.id,
                event_type=TicketEventType.ASSIGNED,
                payload_json=build_status_payload(
                    from_status=TicketStatus.QUEUED,
                    to_status=assigned_ticket.status,
                    assigned_operator_id=operator_id,
                    actor_operator_id=operator_id,
                ),
            )
            return build_ticket_summary(
                assigned_ticket, event_type=TicketEventType.ASSIGNED
            )

        return None


class ReplyToTicketAsOperatorUseCase:
    def __init__(
        self,
        ticket_repository: TicketRepository,
        ticket_message_repository: TicketMessageRepository,
        ticket_event_repository: TicketEventRepository,
        operator_repository: OperatorRepository,
    ) -> None:
        self.ticket_repository = ticket_repository
        self.operator_repository = operator_repository
        self._add_message_to_ticket = AddMessageToTicketUseCase(
            ticket_repository=ticket_repository,
            ticket_message_repository=ticket_message_repository,
            ticket_event_repository=ticket_event_repository,
        )

    async def __call__(
        self,
        *,
        ticket_public_id: UUID,
        telegram_user_id: int,
        display_name: str,
        username: str | None,
        telegram_message_id: int,
        text: str,
    ) -> OperatorReplyResult | None:
        ticket_details = await self.ticket_repository.get_details_by_public_id(
            ticket_public_id
        )
        if ticket_details is None:
            return None

        ensure_operator_replyable(ticket_details.status)

        operator_id = await self.operator_repository.get_or_create(
            telegram_user_id=telegram_user_id,
            display_name=display_name,
            username=username,
        )
        if (
            ticket_details.assigned_operator_id is not None
            and ticket_details.assigned_operator_id != operator_id
        ):
            raise InvalidTicketTransitionError("Заявка назначена другому оператору.")

        ticket = await self._add_message_to_ticket(
            ticket_public_id=ticket_public_id,
            telegram_message_id=telegram_message_id,
            sender_type=TicketMessageSenderType.OPERATOR,
            text=text,
            sender_operator_id=operator_id,
        )
        if ticket is None:
            return None

        return OperatorReplyResult(
            ticket=ticket,
            client_chat_id=ticket_details.client_chat_id,
        )


class ListMacrosUseCase:
    def __init__(self, macro_repository: MacroRepository) -> None:
        self.macro_repository = macro_repository

    async def __call__(self) -> Sequence[MacroSummary]:
        macros = await self.macro_repository.list_all()
        return [
            MacroSummary(id=macro.id, title=macro.title, body=macro.body)
            for macro in macros
        ]


class ApplyMacroToTicketUseCase:
    def __init__(
        self,
        ticket_repository: TicketRepository,
        ticket_message_repository: TicketMessageRepository,
        ticket_event_repository: TicketEventRepository,
        operator_repository: OperatorRepository,
        macro_repository: MacroRepository,
    ) -> None:
        self.ticket_repository = ticket_repository
        self.ticket_message_repository = ticket_message_repository
        self.operator_repository = operator_repository
        self.macro_repository = macro_repository
        self._add_message_to_ticket = AddMessageToTicketUseCase(
            ticket_repository=ticket_repository,
            ticket_message_repository=ticket_message_repository,
            ticket_event_repository=ticket_event_repository,
        )

    async def __call__(
        self,
        *,
        ticket_public_id: UUID,
        macro_id: int,
        telegram_user_id: int,
        display_name: str,
        username: str | None,
    ) -> MacroApplicationResult | None:
        ticket_details = await self.ticket_repository.get_details_by_public_id(
            ticket_public_id
        )
        if ticket_details is None:
            return None

        macro = await self.macro_repository.get_by_id(macro_id=macro_id)
        if macro is None:
            return None

        ensure_operator_replyable(ticket_details.status)

        operator_id = await self.operator_repository.get_or_create(
            telegram_user_id=telegram_user_id,
            display_name=display_name,
            username=username,
        )
        if (
            ticket_details.assigned_operator_id is not None
            and ticket_details.assigned_operator_id != operator_id
        ):
            raise InvalidTicketTransitionError("Заявка назначена другому оператору.")

        telegram_message_id = (
            await self.ticket_message_repository.allocate_internal_telegram_message_id(
                ticket_id=ticket_details.id,
                sender_type=TicketMessageSenderType.OPERATOR,
            )
        )
        ticket = await self._add_message_to_ticket(
            ticket_public_id=ticket_public_id,
            telegram_message_id=telegram_message_id,
            sender_type=TicketMessageSenderType.OPERATOR,
            text=macro.body,
            sender_operator_id=operator_id,
            extra_event_payload={
                "macro_id": macro.id,
                "macro_title": macro.title,
            },
        )
        if ticket is None:
            return None

        return MacroApplicationResult(
            ticket=ticket,
            client_chat_id=ticket_details.client_chat_id,
            macro=MacroSummary(id=macro.id, title=macro.title, body=macro.body),
        )


class ListTicketTagsUseCase:
    def __init__(
        self,
        ticket_repository: TicketRepository,
        ticket_tag_repository: TicketTagRepository,
    ) -> None:
        self.ticket_repository = ticket_repository
        self.ticket_tag_repository = ticket_tag_repository

    async def __call__(self, *, ticket_public_id: UUID) -> TicketTagsSummary | None:
        ticket = await self.ticket_repository.get_by_public_id(ticket_public_id)
        if ticket is None or ticket.id is None:
            return None

        tags = await self.ticket_tag_repository.list_for_ticket(ticket_id=ticket.id)
        return TicketTagsSummary(
            public_id=ticket.public_id,
            public_number=format_public_ticket_number(ticket.public_id),
            tags=tuple(tag.name for tag in tags),
        )


class ListAvailableTagsUseCase:
    def __init__(self, tag_repository: TagRepository) -> None:
        self.tag_repository = tag_repository

    async def __call__(self) -> Sequence[str]:
        tags = await self.tag_repository.list_all()
        return [tag.name for tag in tags]


class AddTagToTicketUseCase:
    def __init__(
        self,
        ticket_repository: TicketRepository,
        tag_repository: TagRepository,
        ticket_tag_repository: TicketTagRepository,
        ticket_event_repository: TicketEventRepository,
    ) -> None:
        self.ticket_repository = ticket_repository
        self.tag_repository = tag_repository
        self.ticket_tag_repository = ticket_tag_repository
        self.ticket_event_repository = ticket_event_repository

    async def __call__(
        self,
        *,
        ticket_public_id: UUID,
        tag_name: str,
    ) -> TicketTagMutationResult | None:
        ticket = await self.ticket_repository.get_by_public_id(ticket_public_id)
        if ticket is None or ticket.id is None:
            return None

        tag_id = await self.tag_repository.get_or_create(name=tag_name)
        added = await self.ticket_tag_repository.add(ticket_id=ticket.id, tag_id=tag_id)
        tags = await self.ticket_tag_repository.list_for_ticket(ticket_id=ticket.id)
        normalized_tag = next(
            (tag.name for tag in tags if tag.id == tag_id), tag_name.strip().lower()
        )

        if added:
            await self.ticket_event_repository.add(
                ticket_id=ticket.id,
                event_type=TicketEventType.TAG_ADDED,
                payload_json={"tag": normalized_tag},
            )

        return TicketTagMutationResult(
            ticket=build_ticket_summary(
                ticket, event_type=TicketEventType.TAG_ADDED if added else None
            ),
            tag=normalized_tag,
            changed=added,
            tags=tuple(tag.name for tag in tags),
        )


class RemoveTagFromTicketUseCase:
    def __init__(
        self,
        ticket_repository: TicketRepository,
        tag_repository: TagRepository,
        ticket_tag_repository: TicketTagRepository,
        ticket_event_repository: TicketEventRepository,
    ) -> None:
        self.ticket_repository = ticket_repository
        self.tag_repository = tag_repository
        self.ticket_tag_repository = ticket_tag_repository
        self.ticket_event_repository = ticket_event_repository

    async def __call__(
        self,
        *,
        ticket_public_id: UUID,
        tag_name: str,
    ) -> TicketTagMutationResult | None:
        ticket = await self.ticket_repository.get_by_public_id(ticket_public_id)
        if ticket is None or ticket.id is None:
            return None

        tag = await self.tag_repository.get_by_name(name=tag_name)
        removed = False
        normalized_tag = tag_name.strip().lower()
        if tag is not None:
            normalized_tag = tag.name
            removed = await self.ticket_tag_repository.remove(
                ticket_id=ticket.id, tag_id=tag.id
            )
            if removed:
                await self.ticket_event_repository.add(
                    ticket_id=ticket.id,
                    event_type=TicketEventType.TAG_REMOVED,
                    payload_json={"tag": normalized_tag},
                )

        tags = await self.ticket_tag_repository.list_for_ticket(ticket_id=ticket.id)
        return TicketTagMutationResult(
            ticket=build_ticket_summary(
                ticket,
                event_type=TicketEventType.TAG_REMOVED if removed else None,
            ),
            tag=normalized_tag,
            changed=removed,
            tags=tuple(tag_item.name for tag_item in tags),
        )


class EscalateTicketUseCase:
    def __init__(
        self,
        ticket_repository: TicketRepository,
        ticket_event_repository: TicketEventRepository,
    ) -> None:
        self.ticket_repository = ticket_repository
        self.ticket_event_repository = ticket_event_repository

    async def __call__(self, *, ticket_public_id: UUID) -> TicketSummary | None:
        ticket = await self.ticket_repository.get_by_public_id(ticket_public_id)
        if ticket is None or ticket.id is None:
            return None

        ensure_escalatable(ticket.status)
        previous_status = ticket.status

        escalated_ticket = await self.ticket_repository.escalate(
            ticket_public_id=ticket_public_id
        )
        if escalated_ticket is None:
            return None

        await self.ticket_event_repository.add(
            ticket_id=ticket.id,
            event_type=TicketEventType.ESCALATED,
            payload_json=build_status_payload(
                from_status=previous_status,
                to_status=escalated_ticket.status,
                assigned_operator_id=escalated_ticket.assigned_operator_id,
            ),
        )

        return build_ticket_summary(
            escalated_ticket, event_type=TicketEventType.ESCALATED
        )


class CloseTicketUseCase:
    def __init__(
        self,
        ticket_repository: TicketRepository,
        ticket_event_repository: TicketEventRepository,
    ) -> None:
        self.ticket_repository = ticket_repository
        self.ticket_event_repository = ticket_event_repository

    async def __call__(self, *, ticket_public_id: UUID) -> TicketSummary | None:
        ticket = await self.ticket_repository.get_by_public_id(ticket_public_id)
        if ticket is None or ticket.id is None:
            return None

        ensure_closable(ticket.status)
        previous_status = ticket.status

        closed_ticket = await self.ticket_repository.close(
            ticket_public_id=ticket_public_id
        )
        if closed_ticket is None:
            return None

        await self.ticket_event_repository.add(
            ticket_id=ticket.id,
            event_type=TicketEventType.CLOSED,
            payload_json=build_status_payload(
                from_status=previous_status,
                to_status=closed_ticket.status,
                assigned_operator_id=closed_ticket.assigned_operator_id,
            ),
        )

        return build_ticket_summary(closed_ticket, event_type=TicketEventType.CLOSED)


class BasicStatsUseCase:
    def __init__(self, ticket_repository: TicketRepository) -> None:
        self.ticket_repository = ticket_repository

    async def __call__(self) -> TicketStats:
        by_status = dict(await self.ticket_repository.count_by_status())
        total = sum(by_status.values())
        open_total = sum(
            count
            for status, count in by_status.items()
            if status != TicketStatus.CLOSED
        )
        return TicketStats(total=total, open_total=open_total, by_status=by_status)


class EvaluateTicketSLAStateUseCase:
    def __init__(
        self,
        ticket_repository: TicketRepository,
        sla_policy_repository: SLAPolicyRepository,
    ) -> None:
        self.ticket_repository = ticket_repository
        self.sla_policy_repository = sla_policy_repository

    async def __call__(
        self,
        *,
        ticket_public_id: UUID,
        now: datetime | None = None,
    ) -> TicketSLAEvaluationSummary | None:
        ticket = await self.ticket_repository.get_by_public_id(ticket_public_id)
        if ticket is None:
            return None

        checked_at = now or utcnow()
        policy = await self.sla_policy_repository.get_for_priority(priority=ticket.priority)
        return evaluate_ticket_sla(ticket=ticket, policy=policy, now=checked_at)


class AutoEscalateTicketBySLAUseCase:
    def __init__(
        self,
        ticket_repository: TicketRepository,
        ticket_event_repository: TicketEventRepository,
        sla_policy_repository: SLAPolicyRepository,
    ) -> None:
        self.ticket_repository = ticket_repository
        self.ticket_event_repository = ticket_event_repository
        self.sla_policy_repository = sla_policy_repository

    async def __call__(
        self,
        *,
        ticket_public_id: UUID,
        now: datetime | None = None,
    ) -> TicketSummary | None:
        ticket = await self.ticket_repository.get_by_public_id(ticket_public_id)
        if ticket is None or ticket.id is None:
            return None

        checked_at = now or utcnow()
        policy = await self.sla_policy_repository.get_for_priority(priority=ticket.priority)
        evaluation = evaluate_ticket_sla(ticket=ticket, policy=policy, now=checked_at)
        if not evaluation.should_auto_escalate:
            return None

        persisted_event_types: list[TicketEventType] = []
        if (
            policy is not None
            and evaluation.first_response.status == SLADeadlineStatus.BREACHED
            and not await self.ticket_event_repository.exists(
                ticket_id=ticket.id,
                event_type=TicketEventType.SLA_BREACHED_FIRST_RESPONSE,
            )
        ):
            await self.ticket_event_repository.add(
                ticket_id=ticket.id,
                event_type=TicketEventType.SLA_BREACHED_FIRST_RESPONSE,
                payload_json=build_sla_event_payload(
                    policy=policy,
                    deadline_at=evaluation.first_response.deadline_at,
                    checked_at=checked_at,
                    remaining_seconds=evaluation.first_response.remaining_seconds,
                ),
            )
            persisted_event_types.append(TicketEventType.SLA_BREACHED_FIRST_RESPONSE)

        if (
            policy is not None
            and evaluation.resolution.status == SLADeadlineStatus.BREACHED
            and not await self.ticket_event_repository.exists(
                ticket_id=ticket.id,
                event_type=TicketEventType.SLA_BREACHED_RESOLUTION,
            )
        ):
            await self.ticket_event_repository.add(
                ticket_id=ticket.id,
                event_type=TicketEventType.SLA_BREACHED_RESOLUTION,
                payload_json=build_sla_event_payload(
                    policy=policy,
                    deadline_at=evaluation.resolution.deadline_at,
                    checked_at=checked_at,
                    remaining_seconds=evaluation.resolution.remaining_seconds,
                ),
            )
            persisted_event_types.append(TicketEventType.SLA_BREACHED_RESOLUTION)

        previous_status = ticket.status
        escalated_ticket = await self.ticket_repository.escalate(
            ticket_public_id=ticket_public_id
        )
        if escalated_ticket is None:
            return None

        reasons: list[str] = []
        if evaluation.first_response.status == SLADeadlineStatus.BREACHED:
            reasons.append(TicketEventType.SLA_BREACHED_FIRST_RESPONSE.value)
        if evaluation.resolution.status == SLADeadlineStatus.BREACHED:
            reasons.append(TicketEventType.SLA_BREACHED_RESOLUTION.value)

        await self.ticket_event_repository.add(
            ticket_id=ticket.id,
            event_type=TicketEventType.AUTO_ESCALATED,
            payload_json={
                **build_status_payload(
                    from_status=previous_status,
                    to_status=escalated_ticket.status,
                    assigned_operator_id=escalated_ticket.assigned_operator_id,
                ),
                "reasons": reasons,
                "checked_at": checked_at.isoformat(),
            },
        )
        persisted_event_types.append(TicketEventType.AUTO_ESCALATED)

        return build_ticket_summary(
            escalated_ticket,
            event_type=TicketEventType.AUTO_ESCALATED,
        )


class AutoReassignTicketBySLAUseCase:
    def __init__(
        self,
        ticket_repository: TicketRepository,
        ticket_event_repository: TicketEventRepository,
        operator_repository: OperatorRepository,
        sla_policy_repository: SLAPolicyRepository,
    ) -> None:
        self.ticket_repository = ticket_repository
        self.ticket_event_repository = ticket_event_repository
        self.operator_repository = operator_repository
        self.sla_policy_repository = sla_policy_repository

    async def __call__(
        self,
        *,
        ticket_public_id: UUID,
        telegram_user_id: int,
        display_name: str,
        username: str | None = None,
        now: datetime | None = None,
    ) -> TicketSummary | None:
        ticket = await self.ticket_repository.get_by_public_id(ticket_public_id)
        if ticket is None or ticket.id is None:
            return None

        checked_at = now or utcnow()
        policy = await self.sla_policy_repository.get_for_priority(priority=ticket.priority)
        evaluation = evaluate_ticket_sla(ticket=ticket, policy=policy, now=checked_at)
        if not evaluation.should_auto_reassign:
            return None

        operator_id = await self.operator_repository.get_or_create(
            telegram_user_id=telegram_user_id,
            display_name=display_name,
            username=username,
        )
        previous_status = ticket.status
        previous_operator_id = ticket.assigned_operator_id
        if previous_operator_id == operator_id:
            return None

        reassigned_ticket = await self.ticket_repository.assign_to_operator(
            ticket_public_id=ticket_public_id,
            operator_id=operator_id,
        )
        if reassigned_ticket is None:
            return None

        await self.ticket_event_repository.add(
            ticket_id=ticket.id,
            event_type=TicketEventType.AUTO_REASSIGNED,
            payload_json={
                **build_status_payload(
                    from_status=previous_status,
                    to_status=reassigned_ticket.status,
                    assigned_operator_id=operator_id,
                    previous_operator_id=previous_operator_id,
                ),
                "checked_at": checked_at.isoformat(),
                "reason": "stale_assigned_ticket",
            },
        )

        return build_ticket_summary(
            reassigned_ticket,
            event_type=TicketEventType.AUTO_REASSIGNED,
        )


class RunTicketSLAChecksUseCase:
    def __init__(
        self,
        ticket_repository: TicketRepository,
        ticket_event_repository: TicketEventRepository,
        operator_repository: OperatorRepository,
        sla_policy_repository: SLAPolicyRepository,
    ) -> None:
        self.ticket_repository = ticket_repository
        self.ticket_event_repository = ticket_event_repository
        self.sla_policy_repository = sla_policy_repository
        self._evaluate_ticket_sla_state = EvaluateTicketSLAStateUseCase(
            ticket_repository=ticket_repository,
            sla_policy_repository=sla_policy_repository,
        )
        self._auto_escalate_ticket = AutoEscalateTicketBySLAUseCase(
            ticket_repository=ticket_repository,
            ticket_event_repository=ticket_event_repository,
            sla_policy_repository=sla_policy_repository,
        )
        self._auto_reassign_ticket = AutoReassignTicketBySLAUseCase(
            ticket_repository=ticket_repository,
            ticket_event_repository=ticket_event_repository,
            operator_repository=operator_repository,
            sla_policy_repository=sla_policy_repository,
        )

    async def __call__(
        self,
        *,
        now: datetime | None = None,
        limit: int | None = None,
        reassignment_targets: Sequence[SLAAutoReassignmentTarget] = (),
    ) -> SLABatchProcessingResult:
        checked_at = now or utcnow()
        tickets = await self.ticket_repository.list_open_tickets(limit=limit)
        target_by_public_id = {
            target.ticket_public_id: target for target in reassignment_targets
        }

        processed: list[TicketSLAProcessingSummary] = []
        auto_escalated_count = 0
        auto_reassigned_count = 0

        for ticket in tickets:
            evaluation = await self._evaluate_ticket_sla_state(
                ticket_public_id=ticket.public_id,
                now=checked_at,
            )
            if evaluation is None:
                continue

            persisted_event_types: list[TicketEventType] = []
            if (
                ticket.id is not None
                and evaluation.policy_name is not None
                and evaluation.first_response.status == SLADeadlineStatus.BREACHED
                and not await self.ticket_event_repository.exists(
                    ticket_id=ticket.id,
                    event_type=TicketEventType.SLA_BREACHED_FIRST_RESPONSE,
                )
            ):
                policy = await self.sla_policy_repository.get_for_priority(
                    priority=ticket.priority
                )
                if policy is not None:
                    await self.ticket_event_repository.add(
                        ticket_id=ticket.id,
                        event_type=TicketEventType.SLA_BREACHED_FIRST_RESPONSE,
                        payload_json=build_sla_event_payload(
                            policy=policy,
                            deadline_at=evaluation.first_response.deadline_at,
                            checked_at=checked_at,
                            remaining_seconds=evaluation.first_response.remaining_seconds,
                        ),
                    )
                    persisted_event_types.append(
                        TicketEventType.SLA_BREACHED_FIRST_RESPONSE
                    )

            if (
                ticket.id is not None
                and evaluation.policy_name is not None
                and evaluation.resolution.status == SLADeadlineStatus.BREACHED
                and not await self.ticket_event_repository.exists(
                    ticket_id=ticket.id,
                    event_type=TicketEventType.SLA_BREACHED_RESOLUTION,
                )
            ):
                policy = await self.sla_policy_repository.get_for_priority(
                    priority=ticket.priority
                )
                if policy is not None:
                    await self.ticket_event_repository.add(
                        ticket_id=ticket.id,
                        event_type=TicketEventType.SLA_BREACHED_RESOLUTION,
                        payload_json=build_sla_event_payload(
                            policy=policy,
                            deadline_at=evaluation.resolution.deadline_at,
                            checked_at=checked_at,
                            remaining_seconds=evaluation.resolution.remaining_seconds,
                        ),
                    )
                    persisted_event_types.append(TicketEventType.SLA_BREACHED_RESOLUTION)

            escalated = await self._auto_escalate_ticket(
                ticket_public_id=ticket.public_id,
                now=checked_at,
            )
            if escalated is not None:
                auto_escalated_count += 1
                persisted_event_types.append(TicketEventType.AUTO_ESCALATED)
                processed.append(
                    TicketSLAProcessingSummary(
                        evaluation=evaluation,
                        persisted_event_types=tuple(dict.fromkeys(persisted_event_types)),
                    )
                )
                continue

            reassignment_target = target_by_public_id.get(ticket.public_id)
            if reassignment_target is not None:
                reassigned = await self._auto_reassign_ticket(
                    ticket_public_id=ticket.public_id,
                    telegram_user_id=reassignment_target.telegram_user_id,
                    display_name=reassignment_target.display_name,
                    username=reassignment_target.username,
                    now=checked_at,
                )
                if reassigned is not None:
                    auto_reassigned_count += 1
                    persisted_event_types.append(TicketEventType.AUTO_REASSIGNED)

            processed.append(
                TicketSLAProcessingSummary(
                    evaluation=evaluation,
                    persisted_event_types=tuple(dict.fromkeys(persisted_event_types)),
                )
            )

        return SLABatchProcessingResult(
            processed_tickets=tuple(processed),
            evaluated_count=len(processed),
            auto_escalated_count=auto_escalated_count,
            auto_reassigned_count=auto_reassigned_count,
        )
