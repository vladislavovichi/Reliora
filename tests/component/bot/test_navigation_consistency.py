from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock
from uuid import UUID, uuid4

from application.contracts.actors import RequestActor
from application.use_cases.tickets.summaries import TicketDetailsSummary
from backend.grpc.contracts import HelpdeskBackendClientFactory
from bot.handlers.operator.workflow_ticket_views import handle_back_from_more_action
from bot.texts.operator import build_active_ticket_opened_text
from domain.enums.tickets import TicketStatus
from tests.support.aiogram import CallbackHarness, build_callback_harness
from tests.support.backend import FakeHelpdeskBackendClient, build_backend_client_factory


class TicketDetailsBackendClient(FakeHelpdeskBackendClient):
    def __init__(self, ticket_details: TicketDetailsSummary) -> None:
        self._ticket_details = ticket_details
        self.get_ticket_details_mock = AsyncMock()

    async def get_ticket_details(
        self,
        *,
        ticket_public_id: UUID,
        actor: RequestActor | None = None,
    ) -> TicketDetailsSummary | None:
        await self.get_ticket_details_mock(
            ticket_public_id=ticket_public_id,
            actor=actor,
        )
        return self._ticket_details


def _build_helpdesk_backend_client_factory(
    service: FakeHelpdeskBackendClient,
) -> HelpdeskBackendClientFactory:
    return build_backend_client_factory(service)


def _build_callback(*, ticket_public_id: str) -> CallbackHarness:
    return build_callback_harness(
        user_id=1001,
        data=f"operator:back:{ticket_public_id}",
        with_edit_text=True,
    )


async def test_back_from_more_action_returns_to_current_ticket_surface() -> None:
    ticket_public_id = uuid4()
    callback = _build_callback(ticket_public_id=str(ticket_public_id))
    ticket_details = TicketDetailsSummary(
        public_id=ticket_public_id,
        public_number="HD-AAAA1111",
        client_chat_id=2002,
        status=TicketStatus.ASSIGNED,
        priority="high",
        subject="Нужна помощь с доступом",
        assigned_operator_id=7,
        assigned_operator_name="Иван Петров",
        assigned_operator_telegram_user_id=1001,
        created_at=datetime(2026, 4, 8, 12, 0, tzinfo=UTC),
        tags=("vip",),
        last_message_text="Не могу войти",
        last_message_sender_type=None,
        message_history=(),
    )
    service = TicketDetailsBackendClient(ticket_details)
    global_rate_limiter = SimpleNamespace(allow=AsyncMock(return_value=True))
    operator_presence = SimpleNamespace(touch=AsyncMock())
    operator_active_ticket_store = SimpleNamespace(
        set_active_ticket=AsyncMock(),
        clear_if_matches=AsyncMock(),
    )
    ticket_live_session_store = SimpleNamespace(refresh_session=AsyncMock())

    await handle_back_from_more_action(
        callback=callback.callback,
        callback_data=SimpleNamespace(ticket_public_id=str(ticket_public_id)),
        helpdesk_backend_client_factory=_build_helpdesk_backend_client_factory(service),
        global_rate_limiter=global_rate_limiter,
        operator_presence=operator_presence,
        operator_active_ticket_store=operator_active_ticket_store,
        ticket_live_session_store=ticket_live_session_store,
    )

    callback.answer.assert_awaited_once_with(
        build_active_ticket_opened_text(ticket_details.public_number)
    )
    assert callback.message.edit_text is not None
    callback.message.edit_text.assert_awaited_once_with(ANY, reply_markup=ANY)
    callback.message.answer.assert_not_awaited()
