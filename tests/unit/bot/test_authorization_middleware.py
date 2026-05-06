from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import NoReturn
from unittest.mock import AsyncMock

from aiogram.types import CallbackQuery, Message
from tests.support.aiogram import build_callback_harness, build_message_harness

from application.services.authorization import AuthorizationService, AuthorizationServiceFactory
from bot.keyboards.reply.main_menu import build_main_menu
from bot.middlewares.authorization import AuthorizationMiddleware
from bot.texts.buttons import OPERATORS_BUTTON_TEXT, QUEUE_BUTTON_TEXT
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
    return build_message_harness(user_id=user_id, text=text).message


def build_callback(*, user_id: int, data: str) -> CallbackQuery:
    return build_callback_harness(user_id=user_id, data=data).callback


async def test_authorization_middleware_denies_regular_user_operator_command() -> None:
    middleware = AuthorizationMiddleware()
    handler = AsyncMock()
    message = build_message_harness(user_id=2002, text=QUEUE_BUTTON_TEXT)

    result = await middleware(
        handler,
        message.message,
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
    message.answer.assert_awaited_once_with(
        "Доступно только операторам и суперадминистраторам.",
        reply_markup=build_main_menu(UserRole.USER),
    )


async def test_authorization_middleware_denies_regular_user_operator_callback() -> None:
    middleware = AuthorizationMiddleware()
    handler = AsyncMock()
    callback = build_callback_harness(user_id=2002, data="operator:take:ticket-public-id")

    result = await middleware(
        handler,
        callback.callback,
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
    callback.answer.assert_awaited_once_with(
        "Доступно только операторам и суперадминистраторам.",
        show_alert=True,
    )


async def test_authorization_middleware_allows_operator_command_and_sets_role_context() -> None:
    middleware = AuthorizationMiddleware()
    handler = AsyncMock(return_value="handled")
    message = build_message_harness(user_id=1001, text=QUEUE_BUTTON_TEXT)
    data = {
        "authorization_service_factory": build_authorization_service_factory(
            active_operator_ids={1001}
        ),
        "event_user_id": 1001,
        "state": None,
    }

    result = await middleware(handler, message.message, data)

    assert result == "handled"
    handler.assert_awaited_once()
    message.answer.assert_not_awaited()
    assert data["event_user_role"] == UserRole.OPERATOR
    assert data["event_is_super_admin"] is False


async def test_authorization_middleware_marks_super_admin_context() -> None:
    middleware = AuthorizationMiddleware()
    handler = AsyncMock(return_value="handled")
    message = build_message(user_id=42, text=OPERATORS_BUTTON_TEXT)
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


async def test_authorization_middleware_denies_revoked_operator_on_next_request() -> None:
    active_operator_ids = {1001}
    middleware = AuthorizationMiddleware()
    handler = AsyncMock(return_value="handled")
    authorization_service_factory = build_authorization_service_factory(
        active_operator_ids=active_operator_ids
    )

    first_message = build_message(user_id=1001, text=QUEUE_BUTTON_TEXT)
    first_data = {
        "authorization_service_factory": authorization_service_factory,
        "event_user_id": 1001,
        "state": None,
    }

    first_result = await middleware(handler, first_message, first_data)

    assert first_result == "handled"
    assert first_data["event_user_role"] == UserRole.OPERATOR

    active_operator_ids.remove(1001)
    handler.reset_mock()

    second_message = build_message_harness(user_id=1001, text=QUEUE_BUTTON_TEXT)
    second_data = {
        "authorization_service_factory": authorization_service_factory,
        "event_user_id": 1001,
        "state": None,
    }

    second_result = await middleware(handler, second_message.message, second_data)

    assert second_result is None
    handler.assert_not_awaited()
    assert second_data["event_user_role"] == UserRole.USER
    second_message.answer.assert_awaited_once_with(
        "Доступно только операторам и суперадминистраторам.",
        reply_markup=build_main_menu(UserRole.USER),
    )
