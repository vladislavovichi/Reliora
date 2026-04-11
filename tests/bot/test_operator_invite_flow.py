from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

from aiogram.filters.command import CommandObject
from aiogram.types import CallbackQuery, Chat, Message, User

from bot.handlers.common.system import handle_start
from bot.handlers.user.operator_invites import handle_operator_invite_confirm
from bot.texts.operator_invites import INVITE_ONBOARDING_CONFIRMED_TEXT
from domain.enums.roles import UserRole


def _build_helpdesk_service_factory(
    service: object,
) -> Callable[[], AbstractAsyncContextManager[object]]:
    @asynccontextmanager
    async def provide() -> AsyncIterator[object]:
        yield service

    return provide


def _build_message() -> Message:
    message = Message.model_construct(
        message_id=10,
        date=datetime.now(UTC),
        chat=Chat.model_construct(id=3001, type="private"),
        from_user=User.model_construct(
            id=3001,
            is_bot=False,
            first_name="Anna",
            username="anna_support",
        ),
        text="/start opr_test",
    )
    object.__setattr__(message, "answer", AsyncMock())
    object.__setattr__(message, "edit_text", AsyncMock())
    return message


def _build_callback() -> CallbackQuery:
    message = _build_message()
    callback = CallbackQuery.model_construct(
        id="callback-id",
        from_user=User.model_construct(
            id=3001,
            is_bot=False,
            first_name="Anna",
            username="anna_support",
        ),
        chat_instance="chat-instance",
        data="operator_invite:confirm",
        message=message,
    )
    object.__setattr__(callback, "answer", AsyncMock())
    return callback


async def test_handle_start_with_invite_code_opens_onboarding_prompt() -> None:
    message = _build_message()
    state = SimpleNamespace(
        set_state=AsyncMock(),
        update_data=AsyncMock(),
    )
    service = SimpleNamespace(
        preview_operator_invite=AsyncMock(
            return_value=SimpleNamespace(
                expires_at=datetime(2026, 4, 15, 12, 0, tzinfo=UTC),
                remaining_uses=1,
            )
        )
    )

    await handle_start(
        message=message,
        command=CommandObject(prefix="/", command="start", mention=None, args="opr_test"),
        state=state,
        helpdesk_service_factory=_build_helpdesk_service_factory(service),
        event_user_role=UserRole.USER,
    )

    state.set_state.assert_awaited()
    message_answer = cast(AsyncMock, message.answer)
    message_answer.assert_awaited_once()
    assert message_answer.await_args is not None
    assert "Приглашение оператора подтверждено." in message_answer.await_args.args[0]


async def test_handle_operator_invite_confirm_redeems_invite_and_opens_operator_menu() -> None:
    callback = _build_callback()
    state = SimpleNamespace(
        get_data=AsyncMock(
            return_value={
                "operator_invite_code": "opr_test",
                "operator_invite_display_name": "Анна Смирнова",
            }
        ),
        clear=AsyncMock(),
    )
    service = SimpleNamespace(
        redeem_operator_invite=AsyncMock(
            return_value=SimpleNamespace(
                operator=SimpleNamespace(operator=SimpleNamespace(display_name="Анна Смирнова")),
                expires_at=datetime(2026, 4, 15, 12, 0, tzinfo=UTC),
            )
        )
    )

    await handle_operator_invite_confirm(
        callback=callback,
        state=state,
        helpdesk_service_factory=_build_helpdesk_service_factory(service),
    )

    callback_answer = cast(AsyncMock, callback.answer)
    callback_answer.assert_awaited_once_with(INVITE_ONBOARDING_CONFIRMED_TEXT)
    assert isinstance(callback.message, Message)
    callback_message_edit = cast(AsyncMock, callback.message.edit_text)
    callback_message_edit.assert_awaited_once()
    callback_message_answer = cast(AsyncMock, callback.message.answer)
    callback_message_answer.assert_awaited_once()
    assert callback_message_answer.await_args is not None
    reply_markup = callback_message_answer.await_args.kwargs["reply_markup"]
    assert reply_markup.keyboard[0][0].text == "Очередь"
