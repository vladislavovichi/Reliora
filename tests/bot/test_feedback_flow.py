from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

from aiogram.types import CallbackQuery, Chat, Message, User

from application.services.helpdesk.service import HelpdeskService, HelpdeskServiceFactory
from application.use_cases.tickets.summaries import (
    TicketDetailsSummary,
    TicketFeedbackMutationResult,
    TicketFeedbackMutationStatus,
    TicketFeedbackSummary,
)
from bot.handlers.user.feedback import (
    handle_ticket_feedback_comment,
    handle_ticket_feedback_comment_prompt,
    handle_ticket_feedback_rating,
    handle_ticket_feedback_skip,
)
from bot.handlers.user.states import UserFeedbackStates
from bot.keyboards.inline.feedback import build_ticket_feedback_comment_markup
from bot.texts.feedback import (
    TICKET_FEEDBACK_COMMENT_PROMPT_TEXT,
    TICKET_FEEDBACK_COMMENT_SAVED_TEXT,
    TICKET_FEEDBACK_SKIPPED_TEXT,
    TICKET_FEEDBACK_THANK_YOU_TEXT,
)
from domain.enums.tickets import TicketStatus


def build_helpdesk_service_factory(service: object) -> HelpdeskServiceFactory:
    @asynccontextmanager
    async def provide() -> AsyncIterator[HelpdeskService]:
        yield cast(HelpdeskService, service)

    return provide


def build_feedback_callback(
    *,
    ticket_public_id: str,
    action: str,
    rating: int = 0,
) -> CallbackQuery:
    message = Message.model_construct(
        message_id=1,
        date=datetime.now(UTC),
        chat=Chat.model_construct(id=2002, type="private"),
        from_user=User.model_construct(id=2002, is_bot=False, first_name="Client"),
        text="stub",
    )
    object.__setattr__(message, "answer", AsyncMock())
    object.__setattr__(message, "edit_reply_markup", AsyncMock())
    object.__setattr__(message, "edit_text", AsyncMock())

    callback = CallbackQuery.model_construct(
        id="callback-id",
        from_user=User.model_construct(id=2002, is_bot=False, first_name="Client"),
        chat_instance="chat-instance",
        data=f"client_feedback:{action}:{ticket_public_id}:{rating}",
        message=message,
    )
    object.__setattr__(callback, "answer", AsyncMock())
    return callback


def build_ticket_details(*, public_id: UUID) -> TicketDetailsSummary:
    return TicketDetailsSummary(
        public_id=public_id,
        public_number="HD-AAAA1111",
        client_chat_id=2002,
        status=TicketStatus.CLOSED,
        priority="normal",
        subject="Нужна помощь",
        assigned_operator_id=7,
        assigned_operator_name="Иван Петров",
        assigned_operator_telegram_user_id=1001,
        created_at=datetime(2026, 4, 8, 12, 0, tzinfo=UTC),
        tags=(),
        last_message_text="Добрый день",
        last_message_sender_type=None,
        message_history=(),
    )


def build_feedback_summary(
    *,
    public_id: UUID,
    rating: int,
    comment: str | None = None,
) -> TicketFeedbackSummary:
    return TicketFeedbackSummary(
        public_id=public_id,
        public_number="HD-AAAA1111",
        client_chat_id=2002,
        rating=rating,
        comment=comment,
        submitted_at=datetime(2026, 4, 8, 12, 30, tzinfo=UTC),
    )


def callback_answer_mock(callback: CallbackQuery) -> AsyncMock:
    return cast(AsyncMock, callback.answer)


def message_answer_mock(callback: CallbackQuery) -> AsyncMock:
    assert isinstance(callback.message, Message)
    return cast(AsyncMock, callback.message.answer)


def message_edit_reply_markup_mock(callback: CallbackQuery) -> AsyncMock:
    assert isinstance(callback.message, Message)
    return cast(AsyncMock, callback.message.edit_reply_markup)


def message_edit_text_mock(callback: CallbackQuery) -> AsyncMock:
    assert isinstance(callback.message, Message)
    return cast(AsyncMock, callback.message.edit_text)


async def test_handle_ticket_feedback_rating_saves_rating_and_offers_comment() -> None:
    ticket_public_id = uuid4()
    callback = build_feedback_callback(
        ticket_public_id=str(ticket_public_id),
        action="rate",
        rating=5,
    )
    feedback = build_feedback_summary(public_id=ticket_public_id, rating=5)
    service = SimpleNamespace(
        submit_ticket_feedback_rating=AsyncMock(
            return_value=TicketFeedbackMutationResult(
                status=TicketFeedbackMutationStatus.CREATED,
                feedback=feedback,
            )
        )
    )
    global_rate_limiter = SimpleNamespace(allow=AsyncMock(return_value=True))

    await handle_ticket_feedback_rating(
        callback=callback,
        callback_data=SimpleNamespace(ticket_public_id=str(ticket_public_id), rating=5),
        helpdesk_service_factory=build_helpdesk_service_factory(service),
        global_rate_limiter=global_rate_limiter,
    )

    service.submit_ticket_feedback_rating.assert_awaited_once_with(
        ticket_public_id=ticket_public_id,
        client_chat_id=2002,
        rating=5,
    )
    message_edit_reply_markup_mock(callback).assert_awaited_once_with(reply_markup=None)
    message_answer_mock(callback).assert_awaited_once_with(
        TICKET_FEEDBACK_THANK_YOU_TEXT,
        reply_markup=build_ticket_feedback_comment_markup(ticket_public_id=ticket_public_id),
    )
    callback_answer_mock(callback).assert_awaited_once_with()


async def test_handle_ticket_feedback_comment_prompt_sets_state_and_edits_message() -> None:
    ticket_public_id = uuid4()
    callback = build_feedback_callback(ticket_public_id=str(ticket_public_id), action="comment")
    feedback = build_feedback_summary(public_id=ticket_public_id, rating=5)
    ticket_details = build_ticket_details(public_id=ticket_public_id)
    service = SimpleNamespace(
        get_ticket_feedback=AsyncMock(return_value=feedback),
        get_ticket_details=AsyncMock(return_value=ticket_details),
    )
    state = SimpleNamespace(set_state=AsyncMock(), set_data=AsyncMock())
    global_rate_limiter = SimpleNamespace(allow=AsyncMock(return_value=True))

    await handle_ticket_feedback_comment_prompt(
        callback=callback,
        callback_data=SimpleNamespace(ticket_public_id=str(ticket_public_id)),
        state=state,
        helpdesk_service_factory=build_helpdesk_service_factory(service),
        global_rate_limiter=global_rate_limiter,
    )

    state.set_state.assert_awaited_once_with(UserFeedbackStates.writing_comment)
    state.set_data.assert_awaited_once_with({"ticket_public_id": str(ticket_public_id)})
    message_edit_text_mock(callback).assert_awaited_once_with(
        TICKET_FEEDBACK_COMMENT_PROMPT_TEXT,
        reply_markup=None,
    )
    callback_answer_mock(callback).assert_awaited_once_with()


async def test_handle_ticket_feedback_skip_closes_prompt_cleanly() -> None:
    ticket_public_id = uuid4()
    callback = build_feedback_callback(ticket_public_id=str(ticket_public_id), action="skip")
    feedback = build_feedback_summary(public_id=ticket_public_id, rating=5)
    ticket_details = build_ticket_details(public_id=ticket_public_id)
    service = SimpleNamespace(
        get_ticket_feedback=AsyncMock(return_value=feedback),
        get_ticket_details=AsyncMock(return_value=ticket_details),
    )
    global_rate_limiter = SimpleNamespace(allow=AsyncMock(return_value=True))

    await handle_ticket_feedback_skip(
        callback=callback,
        callback_data=SimpleNamespace(ticket_public_id=str(ticket_public_id)),
        helpdesk_service_factory=build_helpdesk_service_factory(service),
        global_rate_limiter=global_rate_limiter,
    )

    message_edit_text_mock(callback).assert_awaited_once_with(
        TICKET_FEEDBACK_SKIPPED_TEXT,
        reply_markup=None,
    )
    callback_answer_mock(callback).assert_awaited_once_with()


async def test_handle_ticket_feedback_comment_persists_comment_and_clears_state() -> None:
    ticket_public_id = uuid4()
    message = Message.model_construct(
        message_id=7,
        date=datetime.now(UTC),
        chat=Chat.model_construct(id=2002, type="private"),
        from_user=User.model_construct(id=2002, is_bot=False, first_name="Client"),
        text="Спасибо за помощь",
    )
    object.__setattr__(message, "answer", AsyncMock())

    service = SimpleNamespace(
        add_ticket_feedback_comment=AsyncMock(
            return_value=TicketFeedbackMutationResult(
                status=TicketFeedbackMutationStatus.UPDATED,
                feedback=build_feedback_summary(
                    public_id=ticket_public_id,
                    rating=5,
                    comment="Спасибо за помощь",
                ),
            )
        )
    )
    state = SimpleNamespace(
        get_data=AsyncMock(return_value={"ticket_public_id": str(ticket_public_id)}),
        clear=AsyncMock(),
    )
    global_rate_limiter = SimpleNamespace(allow=AsyncMock(return_value=True))
    chat_rate_limiter = SimpleNamespace(allow=AsyncMock(return_value=True))

    await handle_ticket_feedback_comment(
        message=message,
        state=state,
        helpdesk_service_factory=build_helpdesk_service_factory(service),
        global_rate_limiter=global_rate_limiter,
        chat_rate_limiter=chat_rate_limiter,
    )

    service.add_ticket_feedback_comment.assert_awaited_once_with(
        ticket_public_id=ticket_public_id,
        client_chat_id=2002,
        comment="Спасибо за помощь",
    )
    state.clear.assert_awaited_once_with()
    cast(AsyncMock, message.answer).assert_awaited_once_with(TICKET_FEEDBACK_COMMENT_SAVED_TEXT)
