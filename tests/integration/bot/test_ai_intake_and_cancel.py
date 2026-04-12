from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import ANY, AsyncMock, Mock

from aiogram.types import Chat, Message, User

from application.ai.summaries import AIPredictionConfidence, TicketCategoryPrediction
from application.use_cases.tickets.summaries import TicketCategorySummary
from backend.grpc.contracts import HelpdeskBackendClient, HelpdeskBackendClientFactory
from bot.handlers.user.cancellation import handle_user_cancel
from bot.handlers.user.client import handle_client_text
from bot.handlers.user.states import UserFeedbackStates
from bot.texts.feedback import TICKET_FEEDBACK_COMMENT_CANCELLED_TEXT


def build_helpdesk_backend_client_factory(service: object) -> HelpdeskBackendClientFactory:
    @asynccontextmanager
    async def provide() -> AsyncIterator[HelpdeskBackendClient]:
        yield cast(HelpdeskBackendClient, service)

    return provide


def build_message(*, text: str, chat_id: int = 2002, message_id: int = 15) -> Message:
    message = Message.model_construct(
        message_id=message_id,
        date=datetime.now(UTC),
        chat=Chat.model_construct(id=chat_id, type="private"),
        from_user=User.model_construct(id=chat_id, is_bot=False, first_name="Client"),
        text=text,
    )
    object.__setattr__(message, "answer", AsyncMock())
    return message


async def test_client_intake_uses_category_prediction_when_available() -> None:
    message = build_message(text="Не могу войти после смены пароля")
    state = SimpleNamespace(set_state=AsyncMock(), set_data=AsyncMock())
    service = SimpleNamespace(
        get_client_active_ticket=AsyncMock(return_value=None),
        list_client_ticket_categories=AsyncMock(
            return_value=[
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
        ),
        predict_ticket_category=AsyncMock(
            return_value=TicketCategoryPrediction(
                available=True,
                category_id=1,
                category_code="access",
                category_title="Доступ и вход",
                confidence=AIPredictionConfidence.HIGH,
                reason="Текст явно про восстановление доступа.",
                model_id="Qwen/Qwen3.5-4B",
            )
        ),
    )

    await handle_client_text(
        message=message,
        state=state,
        bot=Mock(),
        helpdesk_backend_client_factory=build_helpdesk_backend_client_factory(service),
        global_rate_limiter=SimpleNamespace(allow=AsyncMock(return_value=True)),
        chat_rate_limiter=SimpleNamespace(allow=AsyncMock(return_value=True)),
        operator_active_ticket_store=SimpleNamespace(get_active_ticket=AsyncMock()),
        ticket_live_session_store=SimpleNamespace(refresh_session=AsyncMock()),
        ticket_stream_publisher=SimpleNamespace(publish_new_ticket=AsyncMock()),
    )

    service.predict_ticket_category.assert_awaited_once()
    cast(AsyncMock, message.answer).assert_awaited_once_with(
        "Похоже, это тема «Доступ и вход».\n"
        "Текст явно про восстановление доступа.\n"
        "Подтвердите вариант или выберите другую тему.",
        reply_markup=ANY,
    )


async def test_user_cancel_clears_feedback_state() -> None:
    message = build_message(text="Отмена")
    state = SimpleNamespace(
        get_state=AsyncMock(return_value=UserFeedbackStates.writing_comment.state),
        get_data=AsyncMock(return_value={}),
        clear=AsyncMock(),
    )

    await handle_user_cancel(message=message, state=state)

    state.clear.assert_awaited_once_with()
    cast(AsyncMock, message.answer).assert_awaited_once_with(
        TICKET_FEEDBACK_COMMENT_CANCELLED_TEXT,
        reply_markup=ANY,
    )
