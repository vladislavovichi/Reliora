from __future__ import annotations

from uuid import UUID

from application.ai.summaries import (
    TicketAssistSnapshot,
    TicketCategoryPrediction,
    TicketReplyDraft,
)
from application.contracts.actors import RequestActor, actor_telegram_user_id
from application.contracts.ai import PredictTicketCategoryCommand
from application.services.authorization import Permission
from application.services.helpdesk._context import _HelpdeskContext


class HelpdeskAIOperations:
    def __init__(self, ctx: _HelpdeskContext) -> None:
        self._ctx = ctx

    async def get_ticket_ai_assist_snapshot(
        self,
        *,
        ticket_public_id: UUID,
        refresh_summary: bool = False,
        actor: RequestActor | None = None,
    ) -> TicketAssistSnapshot | None:
        await self._ctx.require_permission_if_actor(
            permission=Permission.ACCESS_OPERATOR,
            actor_telegram_user_id=actor_telegram_user_id(actor),
        )
        return await self._ctx.components.ai.build_ticket_assist_snapshot(
            ticket_public_id=ticket_public_id,
            refresh_summary=refresh_summary,
        )

    async def predict_ticket_category(
        self,
        command: PredictTicketCategoryCommand,
        *,
        actor: RequestActor | None = None,
    ) -> TicketCategoryPrediction:
        # Category prediction is client-intake assistance, so actor is accepted
        # for transport symmetry but intentionally does not gate access.
        del actor
        return await self._ctx.components.ai.predict_ticket_category(command)

    async def generate_ticket_reply_draft(
        self,
        *,
        ticket_public_id: UUID,
        actor: RequestActor | None = None,
    ) -> TicketReplyDraft | None:
        await self._ctx.require_permission_if_actor(
            permission=Permission.ACCESS_OPERATOR,
            actor_telegram_user_id=actor_telegram_user_id(actor),
        )
        return await self._ctx.components.ai.generate_ticket_reply_draft(
            ticket_public_id=ticket_public_id,
        )
