from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from application.use_cases.tickets import (
    AddMessageToTicketUseCase,
    AddTagToTicketUseCase,
    ApplyMacroToTicketUseCase,
    AssignNextQueuedTicketUseCase,
    AssignTicketToOperatorUseCase,
    AutoEscalateTicketBySLAUseCase,
    AutoReassignTicketBySLAUseCase,
    BasicStatsUseCase,
    CloseTicketUseCase,
    CreateTicketFromClientMessageUseCase,
    EscalateTicketUseCase,
    EvaluateTicketSLAStateUseCase,
    GetNextQueuedTicketUseCase,
    GetTicketDetailsUseCase,
    ListAvailableTagsUseCase,
    ListMacrosUseCase,
    ListQueuedTicketsUseCase,
    ListTicketTagsUseCase,
    MacroApplicationResult,
    MacroSummary,
    OperatorReplyResult,
    QueuedTicketSummary,
    RemoveTagFromTicketUseCase,
    ReplyToTicketAsOperatorUseCase,
    RunTicketSLAChecksUseCase,
    SLAAutoReassignmentTarget,
    SLABatchProcessingResult,
    TicketDetailsSummary,
    TicketSLAEvaluationSummary,
    TicketStats,
    TicketSummary,
    TicketTagMutationResult,
    TicketTagsSummary,
)
from domain.contracts.repositories import (
    MacroRepository,
    OperatorRepository,
    SLAPolicyRepository,
    TagRepository,
    TicketEventRepository,
    TicketMessageRepository,
    TicketRepository,
    TicketTagRepository,
)
from domain.enums.tickets import TicketMessageSenderType
from infrastructure.redis.contracts import SLADeadlineScheduler

HelpdeskServiceFactory = Callable[[], AbstractAsyncContextManager["HelpdeskService"]]


@dataclass(slots=True)
class HelpdeskService:
    ticket_repository: TicketRepository
    ticket_message_repository: TicketMessageRepository
    ticket_event_repository: TicketEventRepository
    operator_repository: OperatorRepository
    macro_repository: MacroRepository
    sla_policy_repository: SLAPolicyRepository
    tag_repository: TagRepository
    ticket_tag_repository: TicketTagRepository
    sla_deadline_scheduler: SLADeadlineScheduler | None = None
    _create_ticket_from_client_message: CreateTicketFromClientMessageUseCase = field(
        init=False,
        repr=False,
    )
    _add_message_to_ticket: AddMessageToTicketUseCase = field(init=False, repr=False)
    _assign_ticket_to_operator: AssignTicketToOperatorUseCase = field(
        init=False, repr=False
    )
    _get_next_queued_ticket: GetNextQueuedTicketUseCase = field(init=False, repr=False)
    _list_queued_tickets: ListQueuedTicketsUseCase = field(init=False, repr=False)
    _assign_next_queued_ticket: AssignNextQueuedTicketUseCase = field(
        init=False, repr=False
    )
    _get_ticket_details: GetTicketDetailsUseCase = field(init=False, repr=False)
    _reply_to_ticket_as_operator: ReplyToTicketAsOperatorUseCase = field(
        init=False,
        repr=False,
    )
    _list_macros: ListMacrosUseCase = field(init=False, repr=False)
    _apply_macro_to_ticket: ApplyMacroToTicketUseCase = field(init=False, repr=False)
    _list_ticket_tags: ListTicketTagsUseCase = field(init=False, repr=False)
    _list_available_tags: ListAvailableTagsUseCase = field(init=False, repr=False)
    _add_tag_to_ticket: AddTagToTicketUseCase = field(init=False, repr=False)
    _remove_tag_from_ticket: RemoveTagFromTicketUseCase = field(init=False, repr=False)
    _escalate_ticket: EscalateTicketUseCase = field(init=False, repr=False)
    _close_ticket: CloseTicketUseCase = field(init=False, repr=False)
    _get_basic_stats: BasicStatsUseCase = field(init=False, repr=False)
    _evaluate_ticket_sla_state: EvaluateTicketSLAStateUseCase = field(
        init=False, repr=False
    )
    _auto_escalate_ticket_by_sla: AutoEscalateTicketBySLAUseCase = field(
        init=False, repr=False
    )
    _auto_reassign_ticket_by_sla: AutoReassignTicketBySLAUseCase = field(
        init=False, repr=False
    )
    _run_ticket_sla_checks: RunTicketSLAChecksUseCase = field(
        init=False, repr=False
    )

    async def _sync_sla_deadline(self, *, ticket_public_id: UUID) -> None:
        if self.sla_deadline_scheduler is None:
            return

        evaluation = await self._evaluate_ticket_sla_state(
            ticket_public_id=ticket_public_id
        )
        if evaluation is None:
            return

        next_deadline_at = min(
            (
                deadline.deadline_at
                for deadline in (
                    evaluation.first_response,
                    evaluation.resolution,
                    evaluation.stale_assignment,
                )
                if deadline.deadline_at is not None
                and deadline.remaining_seconds is not None
                and deadline.remaining_seconds > 0
            ),
            default=None,
        )
        if next_deadline_at is None:
            await self.sla_deadline_scheduler.cancel(ticket_id=str(ticket_public_id))
            return

        await self.sla_deadline_scheduler.schedule(
            ticket_id=str(ticket_public_id),
            deadline_at=next_deadline_at,
        )

    def __post_init__(self) -> None:
        self._create_ticket_from_client_message = CreateTicketFromClientMessageUseCase(
            ticket_repository=self.ticket_repository,
            ticket_message_repository=self.ticket_message_repository,
            ticket_event_repository=self.ticket_event_repository,
        )
        self._add_message_to_ticket = AddMessageToTicketUseCase(
            ticket_repository=self.ticket_repository,
            ticket_message_repository=self.ticket_message_repository,
            ticket_event_repository=self.ticket_event_repository,
        )
        self._assign_ticket_to_operator = AssignTicketToOperatorUseCase(
            ticket_repository=self.ticket_repository,
            ticket_event_repository=self.ticket_event_repository,
            operator_repository=self.operator_repository,
        )
        self._get_next_queued_ticket = GetNextQueuedTicketUseCase(
            ticket_repository=self.ticket_repository,
        )
        self._list_queued_tickets = ListQueuedTicketsUseCase(
            ticket_repository=self.ticket_repository,
        )
        self._assign_next_queued_ticket = AssignNextQueuedTicketUseCase(
            ticket_repository=self.ticket_repository,
            ticket_event_repository=self.ticket_event_repository,
            operator_repository=self.operator_repository,
        )
        self._get_ticket_details = GetTicketDetailsUseCase(
            ticket_repository=self.ticket_repository,
        )
        self._reply_to_ticket_as_operator = ReplyToTicketAsOperatorUseCase(
            ticket_repository=self.ticket_repository,
            ticket_message_repository=self.ticket_message_repository,
            ticket_event_repository=self.ticket_event_repository,
            operator_repository=self.operator_repository,
        )
        self._list_macros = ListMacrosUseCase(macro_repository=self.macro_repository)
        self._apply_macro_to_ticket = ApplyMacroToTicketUseCase(
            ticket_repository=self.ticket_repository,
            ticket_message_repository=self.ticket_message_repository,
            ticket_event_repository=self.ticket_event_repository,
            operator_repository=self.operator_repository,
            macro_repository=self.macro_repository,
        )
        self._list_ticket_tags = ListTicketTagsUseCase(
            ticket_repository=self.ticket_repository,
            ticket_tag_repository=self.ticket_tag_repository,
        )
        self._list_available_tags = ListAvailableTagsUseCase(
            tag_repository=self.tag_repository,
        )
        self._add_tag_to_ticket = AddTagToTicketUseCase(
            ticket_repository=self.ticket_repository,
            tag_repository=self.tag_repository,
            ticket_tag_repository=self.ticket_tag_repository,
            ticket_event_repository=self.ticket_event_repository,
        )
        self._remove_tag_from_ticket = RemoveTagFromTicketUseCase(
            ticket_repository=self.ticket_repository,
            tag_repository=self.tag_repository,
            ticket_tag_repository=self.ticket_tag_repository,
            ticket_event_repository=self.ticket_event_repository,
        )
        self._escalate_ticket = EscalateTicketUseCase(
            ticket_repository=self.ticket_repository,
            ticket_event_repository=self.ticket_event_repository,
        )
        self._close_ticket = CloseTicketUseCase(
            ticket_repository=self.ticket_repository,
            ticket_event_repository=self.ticket_event_repository,
        )
        self._get_basic_stats = BasicStatsUseCase(
            ticket_repository=self.ticket_repository
        )
        self._evaluate_ticket_sla_state = EvaluateTicketSLAStateUseCase(
            ticket_repository=self.ticket_repository,
            sla_policy_repository=self.sla_policy_repository,
        )
        self._auto_escalate_ticket_by_sla = AutoEscalateTicketBySLAUseCase(
            ticket_repository=self.ticket_repository,
            ticket_event_repository=self.ticket_event_repository,
            sla_policy_repository=self.sla_policy_repository,
        )
        self._auto_reassign_ticket_by_sla = AutoReassignTicketBySLAUseCase(
            ticket_repository=self.ticket_repository,
            ticket_event_repository=self.ticket_event_repository,
            operator_repository=self.operator_repository,
            sla_policy_repository=self.sla_policy_repository,
        )
        self._run_ticket_sla_checks = RunTicketSLAChecksUseCase(
            ticket_repository=self.ticket_repository,
            ticket_event_repository=self.ticket_event_repository,
            operator_repository=self.operator_repository,
            sla_policy_repository=self.sla_policy_repository,
        )

    async def create_ticket_from_client_message(
        self,
        *,
        client_chat_id: int,
        telegram_message_id: int,
        text: str,
    ) -> TicketSummary:
        result = await self._create_ticket_from_client_message(
            client_chat_id=client_chat_id,
            telegram_message_id=telegram_message_id,
            text=text,
        )
        await self._sync_sla_deadline(ticket_public_id=result.public_id)
        return result

    async def add_message_to_ticket(
        self,
        *,
        ticket_public_id: UUID,
        telegram_message_id: int,
        sender_type: TicketMessageSenderType,
        text: str,
        sender_operator_id: int | None = None,
    ) -> TicketSummary | None:
        result = await self._add_message_to_ticket(
            ticket_public_id=ticket_public_id,
            telegram_message_id=telegram_message_id,
            sender_type=sender_type,
            text=text,
            sender_operator_id=sender_operator_id,
        )
        if result is not None:
            await self._sync_sla_deadline(ticket_public_id=result.public_id)
        return result

    async def assign_ticket_to_operator(
        self,
        *,
        ticket_public_id: UUID,
        telegram_user_id: int,
        display_name: str,
        username: str | None = None,
    ) -> TicketSummary | None:
        result = await self._assign_ticket_to_operator(
            ticket_public_id=ticket_public_id,
            telegram_user_id=telegram_user_id,
            display_name=display_name,
            username=username,
        )
        if result is not None:
            await self._sync_sla_deadline(ticket_public_id=result.public_id)
        return result

    async def close_ticket(self, *, ticket_public_id: UUID) -> TicketSummary | None:
        result = await self._close_ticket(ticket_public_id=ticket_public_id)
        if result is not None:
            await self._sync_sla_deadline(ticket_public_id=result.public_id)
        return result

    async def get_next_queued_ticket(
        self,
        *,
        prioritize_priority: bool = False,
    ) -> QueuedTicketSummary | None:
        return await self._get_next_queued_ticket(
            prioritize_priority=prioritize_priority
        )

    async def list_queued_tickets(
        self,
        *,
        limit: int | None = None,
        prioritize_priority: bool = False,
    ) -> Sequence[QueuedTicketSummary]:
        return await self._list_queued_tickets(
            limit=limit,
            prioritize_priority=prioritize_priority,
        )

    async def assign_next_ticket_to_operator(
        self,
        *,
        telegram_user_id: int,
        display_name: str,
        username: str | None = None,
        prioritize_priority: bool = False,
    ) -> TicketSummary | None:
        result = await self._assign_next_queued_ticket(
            telegram_user_id=telegram_user_id,
            display_name=display_name,
            username=username,
            prioritize_priority=prioritize_priority,
        )
        if result is not None:
            await self._sync_sla_deadline(ticket_public_id=result.public_id)
        return result

    async def get_ticket_details(
        self,
        *,
        ticket_public_id: UUID,
    ) -> TicketDetailsSummary | None:
        return await self._get_ticket_details(ticket_public_id=ticket_public_id)

    async def reply_to_ticket_as_operator(
        self,
        *,
        ticket_public_id: UUID,
        telegram_user_id: int,
        display_name: str,
        username: str | None,
        telegram_message_id: int,
        text: str,
    ) -> OperatorReplyResult | None:
        result = await self._reply_to_ticket_as_operator(
            ticket_public_id=ticket_public_id,
            telegram_user_id=telegram_user_id,
            display_name=display_name,
            username=username,
            telegram_message_id=telegram_message_id,
            text=text,
        )
        if result is not None:
            await self._sync_sla_deadline(ticket_public_id=result.ticket.public_id)
        return result

    async def list_macros(self) -> Sequence[MacroSummary]:
        return await self._list_macros()

    async def apply_macro_to_ticket(
        self,
        *,
        ticket_public_id: UUID,
        macro_id: int,
        telegram_user_id: int,
        display_name: str,
        username: str | None,
    ) -> MacroApplicationResult | None:
        result = await self._apply_macro_to_ticket(
            ticket_public_id=ticket_public_id,
            macro_id=macro_id,
            telegram_user_id=telegram_user_id,
            display_name=display_name,
            username=username,
        )
        if result is not None:
            await self._sync_sla_deadline(ticket_public_id=result.ticket.public_id)
        return result

    async def list_ticket_tags(
        self,
        *,
        ticket_public_id: UUID,
    ) -> TicketTagsSummary | None:
        return await self._list_ticket_tags(ticket_public_id=ticket_public_id)

    async def list_available_tags(self) -> Sequence[str]:
        return await self._list_available_tags()

    async def add_tag_to_ticket(
        self,
        *,
        ticket_public_id: UUID,
        tag_name: str,
    ) -> TicketTagMutationResult | None:
        result = await self._add_tag_to_ticket(
            ticket_public_id=ticket_public_id,
            tag_name=tag_name,
        )
        if result is not None:
            await self._sync_sla_deadline(ticket_public_id=result.ticket.public_id)
        return result

    async def remove_tag_from_ticket(
        self,
        *,
        ticket_public_id: UUID,
        tag_name: str,
    ) -> TicketTagMutationResult | None:
        result = await self._remove_tag_from_ticket(
            ticket_public_id=ticket_public_id,
            tag_name=tag_name,
        )
        if result is not None:
            await self._sync_sla_deadline(ticket_public_id=result.ticket.public_id)
        return result

    async def escalate_ticket(self, *, ticket_public_id: UUID) -> TicketSummary | None:
        result = await self._escalate_ticket(ticket_public_id=ticket_public_id)
        if result is not None:
            await self._sync_sla_deadline(ticket_public_id=result.public_id)
        return result

    async def get_basic_stats(self) -> TicketStats:
        return await self._get_basic_stats()

    async def evaluate_ticket_sla_state(
        self,
        *,
        ticket_public_id: UUID,
        now: datetime | None = None,
    ) -> TicketSLAEvaluationSummary | None:
        return await self._evaluate_ticket_sla_state(
            ticket_public_id=ticket_public_id,
            now=now,
        )

    async def auto_escalate_ticket_by_sla(
        self,
        *,
        ticket_public_id: UUID,
        now: datetime | None = None,
    ) -> TicketSummary | None:
        result = await self._auto_escalate_ticket_by_sla(
            ticket_public_id=ticket_public_id,
            now=now,
        )
        if result is not None:
            await self._sync_sla_deadline(ticket_public_id=result.public_id)
        return result

    async def auto_reassign_ticket_by_sla(
        self,
        *,
        ticket_public_id: UUID,
        telegram_user_id: int,
        display_name: str,
        username: str | None = None,
        now: datetime | None = None,
    ) -> TicketSummary | None:
        result = await self._auto_reassign_ticket_by_sla(
            ticket_public_id=ticket_public_id,
            telegram_user_id=telegram_user_id,
            display_name=display_name,
            username=username,
            now=now,
        )
        if result is not None:
            await self._sync_sla_deadline(ticket_public_id=result.public_id)
        return result

    async def run_ticket_sla_checks(
        self,
        *,
        now: datetime | None = None,
        limit: int | None = None,
        reassignment_targets: Sequence[SLAAutoReassignmentTarget] = (),
    ) -> SLABatchProcessingResult:
        result = await self._run_ticket_sla_checks(
            now=now,
            limit=limit,
            reassignment_targets=reassignment_targets,
        )
        for item in result.processed_tickets:
            await self._sync_sla_deadline(ticket_public_id=item.evaluation.public_id)
        return result
