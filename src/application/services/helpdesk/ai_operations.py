from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import UUID

from application.ai.summaries import (
    TicketAssistSnapshot,
    TicketCategoryPrediction,
    TicketReplyDraft,
)
from application.contracts.actors import RequestActor, actor_telegram_user_id
from application.contracts.ai import PredictTicketCategoryCommand
from application.services.authorization import Permission
from application.services.helpdesk.components import HelpdeskComponents


class HelpdeskAIOperations:
    _components: HelpdeskComponents
    _require_permission_if_actor: Callable[..., Awaitable[None]]

    async def get_ticket_ai_assist_snapshot(
        self,
        *,
        ticket_public_id: UUID,
        refresh_summary: bool = False,
        actor: RequestActor | None = None,
    ) -> TicketAssistSnapshot | None:
        await self._require_permission_if_actor(
            permission=Permission.ACCESS_OPERATOR,
            actor_telegram_user_id=actor_telegram_user_id(actor),
        )
        return await self._components.ai.build_ticket_assist_snapshot(
            ticket_public_id=ticket_public_id,
            refresh_summary=refresh_summary,
        )

    async def predict_ticket_category(
        self,
        command: PredictTicketCategoryCommand,
        *,
        actor: RequestActor | None = None,
    ) -> TicketCategoryPrediction:
        del actor
        return await self._components.ai.predict_ticket_category(command)

    async def generate_ticket_reply_draft(
        self,
        *,
        ticket_public_id: UUID,
        actor: RequestActor | None = None,
    ) -> TicketReplyDraft | None:
        await self._require_permission_if_actor(
            permission=Permission.ACCESS_OPERATOR,
            actor_telegram_user_id=actor_telegram_user_id(actor),
        )
        return await self._components.ai.generate_ticket_reply_draft(
            ticket_public_id=ticket_public_id,
        )
