from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, Mock
from uuid import UUID, uuid4

from application.ai.summaries import TicketCategoryPrediction
from application.contracts.actors import RequestActor
from application.contracts.ai import PredictTicketCategoryCommand
from application.contracts.tickets import ClientTicketMessageCommand
from application.use_cases.tickets.summaries import (
    TicketCategorySummary,
    TicketDetailsSummary,
    TicketSummary,
)
from backend.grpc.contracts import HelpdeskBackendClientFactory
from bot.handlers.user.client import handle_client_text
from bot.handlers.user.intake_context import ClientIntakeContext, TicketRuntimeContext
from bot.handlers.user.states import UserIntakeStates
from bot.texts.categories import INTAKE_CATEGORY_PROMPT_TEXT
from bot.texts.client import (
    build_ticket_message_added_text,
    build_ticket_message_recorded_text,
)
from domain.enums.tickets import TicketEventType, TicketStatus
from tests.support.aiogram import MessageHarness, build_message_harness
from tests.support.backend import FakeHelpdeskBackendClient, build_backend_client_factory


class ClientIntakeBackendClient(FakeHelpdeskBackendClient):
    def __init__(
        self,
        *,
        active_ticket: TicketSummary | None = None,
        created_ticket: TicketSummary | None = None,
        ticket_details: TicketDetailsSummary | None = None,
        prediction: TicketCategoryPrediction | None = None,
    ) -> None:
        self._active_ticket = active_ticket
        self._created_ticket = created_ticket
        self._ticket_details = ticket_details
        self._prediction = prediction or TicketCategoryPrediction(available=False)
        self.create_ticket_from_client_message_mock = AsyncMock()

    async def get_client_active_ticket(self, *, client_chat_id: int) -> TicketSummary | None:
        del client_chat_id
        return self._active_ticket

    async def list_client_ticket_categories(self) -> list[TicketCategorySummary]:
        return [
            TicketCategorySummary(
                id=1,
                code="access",
                title="Доступ и вход",
                is_active=True,
                sort_order=10,
            )
        ]

    async def predict_ticket_category(
        self,
        command: PredictTicketCategoryCommand,
        *,
        actor: RequestActor | None = None,
    ) -> TicketCategoryPrediction:
        del command, actor
        return self._prediction

    async def create_ticket_from_client_message(
        self,
        command: ClientTicketMessageCommand,
    ) -> TicketSummary:
        await self.create_ticket_from_client_message_mock(command)
        assert self._created_ticket is not None
        return self._created_ticket

    async def get_ticket_details(
        self,
        *,
        ticket_public_id: UUID,
        actor: RequestActor | None = None,
    ) -> TicketDetailsSummary | None:
        del ticket_public_id, actor
        return self._ticket_details


def build_helpdesk_backend_client_factory(
    service: FakeHelpdeskBackendClient,
) -> HelpdeskBackendClientFactory:
    return build_backend_client_factory(service)


def build_message(
    *,
    text: str,
    chat_id: int = 2002,
    message_id: int = 15,
) -> MessageHarness:
    return build_message_harness(user_id=chat_id, message_id=message_id, text=text)


def build_client_intake_context(service: FakeHelpdeskBackendClient) -> ClientIntakeContext:
    return ClientIntakeContext(
        ticket_runtime=TicketRuntimeContext(
            helpdesk_backend_client_factory=build_helpdesk_backend_client_factory(service),
            operator_active_ticket_store=SimpleNamespace(
                get_active_ticket=AsyncMock(return_value=None)
            ),
            ticket_live_session_store=SimpleNamespace(refresh_session=AsyncMock()),
            ticket_stream_publisher=SimpleNamespace(publish_new_ticket=AsyncMock()),
            logger=Mock(),
        ),
        global_rate_limiter=SimpleNamespace(allow=AsyncMock(return_value=True)),
        chat_rate_limiter=SimpleNamespace(allow=AsyncMock(return_value=True)),
    )


async def test_client_first_message_without_active_ticket_starts_intake_flow() -> None:
    message = build_message(text="Помогите с доступом")
    state = SimpleNamespace(set_state=AsyncMock(), set_data=AsyncMock())
    service = ClientIntakeBackendClient()

    await handle_client_text(
        message=message.message,
        state=state,
        bot=Mock(),
        client_intake_context=build_client_intake_context(service),
    )

    state.set_state.assert_awaited_once_with(UserIntakeStates.choosing_category)
    message.answer.assert_awaited_once_with(
        INTAKE_CATEGORY_PROMPT_TEXT,
        reply_markup=ANY,
    )


async def test_client_message_with_active_ticket_keeps_live_dialogue_path() -> None:
    ticket_public_id = uuid4()
    message = build_message(text="Есть обновления?")
    state = SimpleNamespace(set_state=AsyncMock())
    ticket = TicketSummary(
        public_id=ticket_public_id,
        public_number="HD-AAAA1111",
        status=TicketStatus.ASSIGNED,
        created=False,
    )
    ticket_details = TicketDetailsSummary(
        public_id=ticket_public_id,
        public_number="HD-AAAA1111",
        client_chat_id=2002,
        status=TicketStatus.ASSIGNED,
        priority="normal",
        subject="Нужна помощь",
        assigned_operator_id=None,
        assigned_operator_name=None,
        assigned_operator_telegram_user_id=None,
        created_at=datetime(2026, 4, 8, 12, 0, tzinfo=UTC),
    )
    service = ClientIntakeBackendClient(
        active_ticket=ticket,
        created_ticket=ticket,
        ticket_details=ticket_details,
    )

    await handle_client_text(
        message=message.message,
        state=state,
        bot=Mock(),
        client_intake_context=build_client_intake_context(service),
    )

    service.create_ticket_from_client_message_mock.assert_awaited_once()
    state.set_state.assert_not_called()
    message.answer.assert_awaited_once_with(
        build_ticket_message_added_text(ticket.public_number, operator_connected=False),
        reply_markup=ANY,
    )


async def test_client_duplicate_burst_is_not_forwarded_to_operator_again() -> None:
    ticket_public_id = uuid4()
    message = build_message(text="????????")
    state = SimpleNamespace(set_state=AsyncMock())
    bot = Mock()
    bot.send_message = AsyncMock()
    ticket = TicketSummary(
        public_id=ticket_public_id,
        public_number="HD-AAAA1111",
        status=TicketStatus.ASSIGNED,
        created=False,
        event_type=TicketEventType.CLIENT_MESSAGE_DUPLICATE_COLLAPSED,
    )
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
    service = ClientIntakeBackendClient(
        active_ticket=ticket,
        created_ticket=ticket,
        ticket_details=ticket_details,
    )

    await handle_client_text(
        message=message.message,
        state=state,
        bot=bot,
        client_intake_context=build_client_intake_context(service),
    )

    bot.send_message.assert_not_awaited()
    message.answer.assert_awaited_once_with(
        build_ticket_message_recorded_text(ticket.public_number),
        reply_markup=ANY,
    )
