from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from application.use_cases.tickets.common import build_status_payload, build_ticket_summary
from application.use_cases.tickets.summaries import (
    QueuedTicketSummary,
    TicketDetailsSummary,
    TicketSummary,
    build_queued_ticket_summary,
    build_ticket_details_summary,
)
from domain.contracts.repositories import (
    OperatorRepository,
    TicketEventRepository,
    TicketRepository,
)
from domain.enums.tickets import TicketEventType, TicketStatus
from domain.tickets import InvalidTicketTransitionError, ensure_assignable


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
        if previous_status == TicketStatus.ASSIGNED and previous_operator_id == operator_id:
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
            return build_ticket_summary(assigned_ticket, event_type=TicketEventType.ASSIGNED)

        return None
