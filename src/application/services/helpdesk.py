from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from uuid import UUID

from application.use_cases.tickets import (
    AddMessageToTicketUseCase,
    AddTagToTicketUseCase,
    ApplyMacroToTicketUseCase,
    AssignNextQueuedTicketUseCase,
    AssignTicketToOperatorUseCase,
    BasicStatsUseCase,
    CloseTicketUseCase,
    CreateTicketFromClientMessageUseCase,
    EscalateTicketUseCase,
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
    TicketDetailsSummary,
    TicketStats,
    TicketSummary,
    TicketTagMutationResult,
    TicketTagsSummary,
)
from domain.contracts.repositories import (
    MacroRepository,
    OperatorRepository,
    TagRepository,
    TicketEventRepository,
    TicketMessageRepository,
    TicketRepository,
    TicketTagRepository,
)
from domain.enums.tickets import TicketMessageSenderType

HelpdeskServiceFactory = Callable[[], AbstractAsyncContextManager["HelpdeskService"]]


@dataclass(slots=True)
class HelpdeskService:
    ticket_repository: TicketRepository
    ticket_message_repository: TicketMessageRepository
    ticket_event_repository: TicketEventRepository
    operator_repository: OperatorRepository
    macro_repository: MacroRepository
    tag_repository: TagRepository
    ticket_tag_repository: TicketTagRepository
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

    async def create_ticket_from_client_message(
        self,
        *,
        client_chat_id: int,
        telegram_message_id: int,
        text: str,
    ) -> TicketSummary:
        return await self._create_ticket_from_client_message(
            client_chat_id=client_chat_id,
            telegram_message_id=telegram_message_id,
            text=text,
        )

    async def add_message_to_ticket(
        self,
        *,
        ticket_public_id: UUID,
        telegram_message_id: int,
        sender_type: TicketMessageSenderType,
        text: str,
        sender_operator_id: int | None = None,
    ) -> TicketSummary | None:
        return await self._add_message_to_ticket(
            ticket_public_id=ticket_public_id,
            telegram_message_id=telegram_message_id,
            sender_type=sender_type,
            text=text,
            sender_operator_id=sender_operator_id,
        )

    async def assign_ticket_to_operator(
        self,
        *,
        ticket_public_id: UUID,
        telegram_user_id: int,
        display_name: str,
        username: str | None = None,
    ) -> TicketSummary | None:
        return await self._assign_ticket_to_operator(
            ticket_public_id=ticket_public_id,
            telegram_user_id=telegram_user_id,
            display_name=display_name,
            username=username,
        )

    async def close_ticket(self, *, ticket_public_id: UUID) -> TicketSummary | None:
        return await self._close_ticket(ticket_public_id=ticket_public_id)

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
        return await self._assign_next_queued_ticket(
            telegram_user_id=telegram_user_id,
            display_name=display_name,
            username=username,
            prioritize_priority=prioritize_priority,
        )

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
        return await self._reply_to_ticket_as_operator(
            ticket_public_id=ticket_public_id,
            telegram_user_id=telegram_user_id,
            display_name=display_name,
            username=username,
            telegram_message_id=telegram_message_id,
            text=text,
        )

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
        return await self._apply_macro_to_ticket(
            ticket_public_id=ticket_public_id,
            macro_id=macro_id,
            telegram_user_id=telegram_user_id,
            display_name=display_name,
            username=username,
        )

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
        return await self._add_tag_to_ticket(
            ticket_public_id=ticket_public_id,
            tag_name=tag_name,
        )

    async def remove_tag_from_ticket(
        self,
        *,
        ticket_public_id: UUID,
        tag_name: str,
    ) -> TicketTagMutationResult | None:
        return await self._remove_tag_from_ticket(
            ticket_public_id=ticket_public_id,
            tag_name=tag_name,
        )

    async def escalate_ticket(self, *, ticket_public_id: UUID) -> TicketSummary | None:
        return await self._escalate_ticket(ticket_public_id=ticket_public_id)

    async def get_basic_stats(self) -> TicketStats:
        return await self._get_basic_stats()
