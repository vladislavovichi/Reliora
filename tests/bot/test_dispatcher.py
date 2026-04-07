from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import NoReturn
from unittest.mock import AsyncMock

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import MagicData
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import Chat, Message, Update, User
from redis.asyncio import Redis

from application.services.authorization import AuthorizationService, AuthorizationServiceFactory
from bot.dispatcher import _register_middlewares, build_dispatcher
from infrastructure.redis.fsm import build_fsm_storage
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


def build_message_update(*, user_id: int, text: str) -> Update:
    return Update.model_construct(
        update_id=1,
        message=Message.model_construct(
            message_id=1,
            date=datetime.now(UTC),
            chat=Chat.model_construct(id=user_id, type="private"),
            from_user=User.model_construct(id=user_id, is_bot=False, first_name="Test"),
            text=text,
        ),
    )


def test_build_fsm_storage_returns_redis_storage() -> None:
    redis = Redis.from_url("redis://localhost:6379/0")
    storage = build_fsm_storage(redis)

    assert isinstance(storage, RedisStorage)
    assert storage.redis is redis


def test_build_dispatcher_uses_provided_storage() -> None:
    redis = Redis.from_url("redis://localhost:6379/0")
    storage = build_fsm_storage(redis)

    dispatcher = build_dispatcher(storage=storage)

    assert dispatcher.storage is storage
    assert len(dispatcher.observers["error"].handlers) == 1


async def test_role_based_magic_data_filter_receives_role_from_outer_middleware() -> None:
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.workflow_data["authorization_service_factory"] = build_authorization_service_factory(
        active_operator_ids=set()
    )
    _register_middlewares(dispatcher)

    router = Router(name="test_magic_data")
    handled = AsyncMock()

    @router.message(MagicData(F.event_user_role == UserRole.USER), F.text)
    async def handle_user_message(message: Message) -> None:
        await handled(message.text)

    dispatcher.include_router(router)
    bot = Bot("123456:token")

    try:
        await dispatcher.feed_update(bot, build_message_update(user_id=2002, text="Привет"))
    finally:
        await bot.session.close()

    handled.assert_awaited_once_with("Привет")
