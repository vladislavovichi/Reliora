from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, Mock

from application.ai.summaries import AIPredictionConfidence, TicketCategoryPrediction
from application.contracts.actors import RequestActor
from application.contracts.ai import PredictTicketCategoryCommand
from application.use_cases.tickets.summaries import TicketCategorySummary
from backend.grpc.contracts import HelpdeskBackendClientFactory
from bot.handlers.user.cancellation import handle_user_cancel
from bot.handlers.user.client import handle_client_text
from bot.handlers.user.intake_context import ClientIntakeContext, TicketRuntimeContext
from bot.handlers.user.states import UserFeedbackStates
from bot.texts.feedback import TICKET_FEEDBACK_COMMENT_CANCELLED_TEXT
from tests.support.aiogram import MessageHarness, build_message_harness
from tests.support.backend import FakeHelpdeskBackendClient, build_backend_client_factory


class AIIntakeBackendClient(FakeHelpdeskBackendClient):
    def __init__(self, prediction: TicketCategoryPrediction) -> None:
        self.predict_ticket_category_mock = AsyncMock()
        self._prediction = prediction

    async def get_client_active_ticket(self, *, client_chat_id: int) -> None:
        del client_chat_id
        return None

    async def list_client_ticket_categories(self) -> list[TicketCategorySummary]:
        return [
            TicketCategorySummary(
                id=1,
                code="access",
                title="Доступ и вход",
                is_active=True,
                sort_order=10,
            ),
            TicketCategorySummary(
                id=2,
                code="billing",
                title="Оплата и баланс",
                is_active=True,
                sort_order=20,
            ),
        ]

    async def predict_ticket_category(
        self,
        command: PredictTicketCategoryCommand,
        *,
        actor: RequestActor | None = None,
    ) -> TicketCategoryPrediction:
        await self.predict_ticket_category_mock(command, actor=actor)
        return self._prediction


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
    return build_message_harness(
        user_id=chat_id,
        message_id=message_id,
        text=text,
    )


def build_client_intake_context(service: FakeHelpdeskBackendClient) -> ClientIntakeContext:
    return ClientIntakeContext(
        ticket_runtime=TicketRuntimeContext(
            helpdesk_backend_client_factory=build_helpdesk_backend_client_factory(service),
            operator_active_ticket_store=SimpleNamespace(get_active_ticket=AsyncMock()),
            ticket_live_session_store=SimpleNamespace(refresh_session=AsyncMock()),
            ticket_stream_publisher=SimpleNamespace(publish_new_ticket=AsyncMock()),
            logger=Mock(),
        ),
        global_rate_limiter=SimpleNamespace(allow=AsyncMock(return_value=True)),
        chat_rate_limiter=SimpleNamespace(allow=AsyncMock(return_value=True)),
    )


async def test_client_intake_uses_category_prediction_when_available() -> None:
    message = build_message(text="Не могу войти после смены пароля")
    state = SimpleNamespace(set_state=AsyncMock(), set_data=AsyncMock())
    service = AIIntakeBackendClient(
        TicketCategoryPrediction(
            available=True,
            category_id=1,
            category_code="access",
            category_title="Доступ и вход",
            confidence=AIPredictionConfidence.HIGH,
            reason="Текст явно про восстановление доступа.",
            model_id="Qwen/Qwen3.5-4B",
        )
    )

    await handle_client_text(
        message=message.message,
        state=state,
        bot=Mock(),
        client_intake_context=build_client_intake_context(service),
    )

    service.predict_ticket_category_mock.assert_awaited_once()
    message.answer.assert_awaited_once_with(
        "Похоже, подойдёт тема «Доступ и вход».\n"
        "Почему так: Текст явно про восстановление доступа.\n"
        "Подтвердите вариант или выберите другую тему.",
        reply_markup=ANY,
    )


async def test_user_cancel_clears_feedback_state() -> None:
    message = build_message(text="Отмена")
    state = SimpleNamespace(
        get_state=AsyncMock(return_value=UserFeedbackStates.writing_comment.state),
        get_data=AsyncMock(return_value={}),
        set_data=AsyncMock(),
        set_state=AsyncMock(),
        clear=AsyncMock(),
    )

    await handle_user_cancel(message=message.message, state=state)

    state.set_data.assert_awaited_once_with({})
    state.set_state.assert_awaited_once_with(None)
    state.clear.assert_awaited_once_with()
    message.answer.assert_awaited_once_with(
        TICKET_FEEDBACK_COMMENT_CANCELLED_TEXT,
        reply_markup=ANY,
    )
