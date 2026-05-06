from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, Mock
from uuid import UUID, uuid4

from application.contracts.actors import RequestActor
from application.contracts.tickets import OperatorTicketReplyCommand
from application.use_cases.tickets.summaries import (
    OperatorReplyResult,
    TicketDetailsSummary,
    TicketSummary,
)
from backend.grpc.contracts import HelpdeskBackendClientFactory
from bot.handlers.operator.workflow_reply import _handle_operator_message
from bot.texts.operator import build_reply_sent_text
from domain.enums.tickets import TicketStatus
from tests.support.aiogram import MessageHarness, build_message_harness
from tests.support.backend import FakeHelpdeskBackendClient, build_backend_client_factory


class LiveReplyBackendClient(FakeHelpdeskBackendClient):
    def __init__(
        self,
        *,
        ticket_details: TicketDetailsSummary,
        reply_result: OperatorReplyResult,
    ) -> None:
        self._ticket_details = ticket_details
        self._reply_result = reply_result
        self.get_ticket_details_mock = AsyncMock()
        self.reply_to_ticket_as_operator_mock = AsyncMock()

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

    async def reply_to_ticket_as_operator(
        self,
        command: OperatorTicketReplyCommand,
        actor: RequestActor | None = None,
    ) -> OperatorReplyResult | None:
        await self.reply_to_ticket_as_operator_mock(command, actor=actor)
        return self._reply_result


def _build_helpdesk_backend_client_factory(
    service: FakeHelpdeskBackendClient,
) -> HelpdeskBackendClientFactory:
    return build_backend_client_factory(service)


def _build_message() -> MessageHarness:
    return build_message_harness(
        user_id=1001,
        chat_id=3001,
        message_id=20,
        text="Держу вас в курсе",
    )


async def test_operator_reply_refreshes_action_surface_after_successful_live_message() -> None:
    ticket_public_id = uuid4()
    message = _build_message()
    ticket_details = TicketDetailsSummary(
        public_id=ticket_public_id,
        public_number="HD-AAAA1111",
        client_chat_id=2002,
        status=TicketStatus.ASSIGNED,
        priority="normal",
        subject="Нужна помощь",
        assigned_operator_id=7,
        assigned_operator_name="Иван Петров",
        assigned_operator_telegram_user_id=1001,
        created_at=datetime(2026, 4, 8, 12, 0, tzinfo=UTC),
    )
    reply_result = OperatorReplyResult(
        ticket=TicketSummary(
            public_id=ticket_public_id,
            public_number="HD-AAAA1111",
            status=TicketStatus.ASSIGNED,
            created=False,
        ),
        client_chat_id=2002,
    )
    service = LiveReplyBackendClient(ticket_details=ticket_details, reply_result=reply_result)
    bot = Mock()
    bot.send_message = AsyncMock()
    lock = SimpleNamespace(acquire=AsyncMock(return_value=True), release=AsyncMock())

    await _handle_operator_message(
        message=message.message,
        bot=bot,
        helpdesk_backend_client_factory=_build_helpdesk_backend_client_factory(service),
        global_rate_limiter=SimpleNamespace(allow=AsyncMock(return_value=True)),
        operator_presence=SimpleNamespace(touch=AsyncMock()),
        operator_active_ticket_store=SimpleNamespace(
            set_active_ticket=AsyncMock(),
            clear_if_matches=AsyncMock(),
            get_active_ticket=AsyncMock(return_value=str(ticket_public_id)),
        ),
        ticket_live_session_store=SimpleNamespace(refresh_session=AsyncMock()),
        ticket_lock_manager=SimpleNamespace(for_ticket=Mock(return_value=lock)),
        explicit_ticket_public_id=ticket_public_id,
    )

    message.answer.assert_awaited_once_with(
        build_reply_sent_text(reply_result.ticket.public_number),
        reply_markup=ANY,
    )
