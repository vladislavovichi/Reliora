from __future__ import annotations

from uuid import UUID

from application.use_cases.tickets.identifiers import format_public_ticket_number
from application.use_cases.tickets.summaries import (
    TicketFeedbackMutationResult,
    TicketFeedbackMutationStatus,
    TicketFeedbackSummary,
)
from domain.contracts.repositories import TicketFeedbackRepository, TicketRepository
from domain.entities.feedback import TicketFeedback
from domain.entities.ticket import Ticket
from domain.enums.tickets import TicketStatus


def build_ticket_feedback_summary(
    *,
    ticket: Ticket,
    feedback: TicketFeedback,
) -> TicketFeedbackSummary:
    return TicketFeedbackSummary(
        public_id=ticket.public_id,
        public_number=format_public_ticket_number(ticket.public_id),
        client_chat_id=feedback.client_chat_id,
        rating=feedback.rating,
        comment=feedback.comment,
        submitted_at=feedback.submitted_at,
    )


class GetTicketFeedbackUseCase:
    def __init__(
        self,
        ticket_repository: TicketRepository,
        ticket_feedback_repository: TicketFeedbackRepository,
    ) -> None:
        self.ticket_repository = ticket_repository
        self.ticket_feedback_repository = ticket_feedback_repository

    async def __call__(self, *, ticket_public_id: UUID) -> TicketFeedbackSummary | None:
        ticket = await self.ticket_repository.get_by_public_id(ticket_public_id)
        if ticket is None or ticket.id is None:
            return None

        feedback = await self.ticket_feedback_repository.get_by_ticket_id(ticket_id=ticket.id)
        if feedback is None:
            return None

        return build_ticket_feedback_summary(ticket=ticket, feedback=feedback)


class SubmitTicketFeedbackRatingUseCase:
    def __init__(
        self,
        ticket_repository: TicketRepository,
        ticket_feedback_repository: TicketFeedbackRepository,
    ) -> None:
        self.ticket_repository = ticket_repository
        self.ticket_feedback_repository = ticket_feedback_repository

    async def __call__(
        self,
        *,
        ticket_public_id: UUID,
        client_chat_id: int,
        rating: int,
    ) -> TicketFeedbackMutationResult:
        ticket = await self.ticket_repository.get_by_public_id(ticket_public_id)
        if ticket is None or ticket.id is None:
            return TicketFeedbackMutationResult(status=TicketFeedbackMutationStatus.NOT_FOUND)
        if ticket.client_chat_id != client_chat_id:
            return TicketFeedbackMutationResult(status=TicketFeedbackMutationStatus.NOT_ALLOWED)
        if ticket.status != TicketStatus.CLOSED:
            return TicketFeedbackMutationResult(status=TicketFeedbackMutationStatus.NOT_CLOSED)

        feedback = await self.ticket_feedback_repository.get_by_ticket_id(ticket_id=ticket.id)
        if feedback is not None:
            return TicketFeedbackMutationResult(
                status=TicketFeedbackMutationStatus.ALREADY_RECORDED,
                feedback=build_ticket_feedback_summary(ticket=ticket, feedback=feedback),
            )

        created_feedback = await self.ticket_feedback_repository.create(
            ticket_id=ticket.id,
            client_chat_id=client_chat_id,
            rating=rating,
        )
        return TicketFeedbackMutationResult(
            status=TicketFeedbackMutationStatus.CREATED,
            feedback=build_ticket_feedback_summary(ticket=ticket, feedback=created_feedback),
        )


class AddTicketFeedbackCommentUseCase:
    def __init__(
        self,
        ticket_repository: TicketRepository,
        ticket_feedback_repository: TicketFeedbackRepository,
    ) -> None:
        self.ticket_repository = ticket_repository
        self.ticket_feedback_repository = ticket_feedback_repository

    async def __call__(
        self,
        *,
        ticket_public_id: UUID,
        client_chat_id: int,
        comment: str,
    ) -> TicketFeedbackMutationResult:
        ticket = await self.ticket_repository.get_by_public_id(ticket_public_id)
        if ticket is None or ticket.id is None:
            return TicketFeedbackMutationResult(status=TicketFeedbackMutationStatus.NOT_FOUND)
        if ticket.client_chat_id != client_chat_id:
            return TicketFeedbackMutationResult(status=TicketFeedbackMutationStatus.NOT_ALLOWED)
        if ticket.status != TicketStatus.CLOSED:
            return TicketFeedbackMutationResult(status=TicketFeedbackMutationStatus.NOT_CLOSED)

        feedback = await self.ticket_feedback_repository.get_by_ticket_id(ticket_id=ticket.id)
        if feedback is None:
            return TicketFeedbackMutationResult(status=TicketFeedbackMutationStatus.MISSING)
        if feedback.comment:
            return TicketFeedbackMutationResult(
                status=TicketFeedbackMutationStatus.ALREADY_RECORDED,
                feedback=build_ticket_feedback_summary(ticket=ticket, feedback=feedback),
            )

        updated_feedback = await self.ticket_feedback_repository.update_comment(
            ticket_id=ticket.id,
            comment=comment.strip(),
        )
        if updated_feedback is None:
            return TicketFeedbackMutationResult(status=TicketFeedbackMutationStatus.MISSING)

        return TicketFeedbackMutationResult(
            status=TicketFeedbackMutationStatus.UPDATED,
            feedback=build_ticket_feedback_summary(ticket=ticket, feedback=updated_feedback),
        )
