from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import NoReturn, cast
from unittest.mock import AsyncMock

from aiogram.types import CallbackQuery, Chat, Message, User

from application.services.authorization import AuthorizationService, AuthorizationServiceFactory
from bot.keyboards.reply.main_menu import build_main_menu
from bot.middlewares.authorization import AuthorizationMiddleware
from domain.enums.roles import UserRole


class FakeOperatorRepository:
    def __init__(self, active_operator_ids: set[int]) -> None:
        self.active_operator_ids = active_operator_ids

    async def exists_active_by_telegram_user_id(self, *, telegram_user_id: int) -> bool:
        return telegram_user_id in self.active_operator_ids

    async def list_active(self) -> NoReturn:
        raise NotImplementedError

    async def promote(
        self,
        *,
        telegram_user_id: int,
        display_name: str,
        username: str | None = None,
    ) -> NoReturn:
        raise NotImplementedError

    async def revoke(self, *, telegram_user_id: int) -> NoReturn:
        raise NotImplementedError

    async def get_or_create(
        self,
        *,
        telegram_user_id: int,
        display_name: str,
        username: str | None = None,
    ) -> NoReturn:
        raise NotImplementedError


def build_authorization_service_factory(
    *,
    active_operator_ids: set[int],
    super_admin_telegram_user_ids: frozenset[int] | None = None,
) -> AuthorizationServiceFactory:
    service = AuthorizationService(
        operator_repository=FakeOperatorRepository(active_operator_ids=active_operator_ids),
        super_admin_telegram_user_ids=super_admin_telegram_user_ids or frozenset({42}),
    )

    @asynccontextmanager
    async def provide() -> AsyncIterator[AuthorizationService]:
        yield service

    return provide


def build_message(*, user_id: int, text: str) -> Message:
    message = Message.model_construct(
        message_id=1,
        date=None,
        chat=Chat.model_construct(id=user_id, type="private"),
        from_user=User.model_construct(id=user_id, is_bot=False, first_name="Test"),
        text=text,
    )
    object.__setattr__(message, "answer", AsyncMock())
    return message


def build_callback(*, user_id: int, data: str) -> CallbackQuery:
    callback = CallbackQuery.model_construct(
        id="callback-id",
        from_user=User.model_construct(id=user_id, is_bot=False, first_name="Test"),
        chat_instance="chat-instance",
        data=data,
        message=build_message(user_id=user_id, text="stub"),
    )
    object.__setattr__(callback, "answer", AsyncMock())
    return callback


def message_answer_mock(message: Message) -> AsyncMock:
    return cast(AsyncMock, message.answer)


def callback_answer_mock(callback: CallbackQuery) -> AsyncMock:
    return cast(AsyncMock, callback.answer)


async def test_authorization_middleware_denies_regular_user_operator_command() -> None:
    middleware = AuthorizationMiddleware()
    handler = AsyncMock()
    message = build_message(user_id=2002, text="/queue")

    result = await middleware(
        handler,
        message,
        {
            "authorization_service_factory": build_authorization_service_factory(
                active_operator_ids=set()
            ),
            "event_user_id": 2002,
            "state": None,
        },
    )

    assert result is None
    handler.assert_not_awaited()
    message_answer_mock(message).assert_awaited_once_with(
        "Это действие доступно только операторам и супер администраторам.",
        reply_markup=build_main_menu(UserRole.USER),
    )


async def test_authorization_middleware_denies_regular_user_operator_callback() -> None:
    middleware = AuthorizationMiddleware()
    handler = AsyncMock()
    callback = build_callback(user_id=2002, data="operator:take:ticket-public-id")

    result = await middleware(
        handler,
        callback,
        {
            "authorization_service_factory": build_authorization_service_factory(
                active_operator_ids=set()
            ),
            "event_user_id": 2002,
            "state": None,
        },
    )

    assert result is None
    handler.assert_not_awaited()
    callback_answer_mock(callback).assert_awaited_once_with(
        "Это действие доступно только операторам и супер администраторам.",
        show_alert=True,
    )


async def test_authorization_middleware_allows_operator_command_and_sets_role_context() -> None:
    middleware = AuthorizationMiddleware()
    handler = AsyncMock(return_value="handled")
    message = build_message(user_id=1001, text="/queue")
    data = {
        "authorization_service_factory": build_authorization_service_factory(
            active_operator_ids={1001}
        ),
        "event_user_id": 1001,
        "state": None,
    }

    result = await middleware(handler, message, data)

    assert result == "handled"
    handler.assert_awaited_once()
    message_answer_mock(message).assert_not_awaited()
    assert data["event_user_role"] == UserRole.OPERATOR
    assert data["event_is_super_admin"] is False


async def test_authorization_middleware_marks_super_admin_context() -> None:
    middleware = AuthorizationMiddleware()
    handler = AsyncMock(return_value="handled")
    message = build_message(user_id=42, text="/operators")
    data = {
        "authorization_service_factory": build_authorization_service_factory(
            active_operator_ids={1001},
            super_admin_telegram_user_ids=frozenset({42}),
        ),
        "event_user_id": 42,
        "state": None,
    }

    result = await middleware(handler, message, data)

    assert result == "handled"
    handler.assert_awaited_once()
    assert data["event_user_role"] == UserRole.SUPER_ADMIN
    assert data["event_is_super_admin"] is True
