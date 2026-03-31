from __future__ import annotations

from uuid import UUID

from application.use_cases.tickets.common import build_status_payload, build_ticket_summary
from application.use_cases.tickets.summaries import TicketStats, TicketSummary
from domain.contracts.repositories import TicketEventRepository, TicketRepository
from domain.enums.tickets import TicketEventType, TicketStatus
from domain.tickets import ensure_closable, ensure_escalatable


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

        escalated_ticket = await self.ticket_repository.escalate(ticket_public_id=ticket_public_id)
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

        return build_ticket_summary(escalated_ticket, event_type=TicketEventType.ESCALATED)


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

        closed_ticket = await self.ticket_repository.close(ticket_public_id=ticket_public_id)
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
            count for status, count in by_status.items() if status != TicketStatus.CLOSED
        )
        return TicketStats(total=total, open_total=open_total, by_status=by_status)
