from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, TypeVar, cast

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import SendMessage, TelegramMethod
from aiogram.types import Chat, Message, Update, User

from bot.dispatcher import build_dispatcher
from bot.texts.system import PING_RESPONSE_TEXT

TelegramType = TypeVar("TelegramType")


def test_dispatcher_processes_synthetic_update_through_fake_bot_api() -> None:
    session = run_dispatcher_ping()

    assert [request.api_method for request in session.requests] == ["sendMessage"]
    request = session.requests[0]
    assert request.payload["chat_id"] == 2002
    assert request.payload["text"] == PING_RESPONSE_TEXT


async def feed_ping_update() -> FakeBotSession:
    session = FakeBotSession()
    bot = Bot(token="123456:ABCDEF", session=session)
    dispatcher = build_dispatcher(storage=MemoryStorage())

    update = build_message_update(text="/ping", chat_id=2002, user_id=2002)

    try:
        await dispatcher.feed_update(bot, update)
    finally:
        await dispatcher.storage.close()
        await bot.session.close()
    return session


def run_dispatcher_ping() -> FakeBotSession:
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(feed_ping_update())
    finally:
        asyncio.set_event_loop(None)
        loop.close()


@dataclass(slots=True)
class BotApiRequest:
    api_method: str
    payload: dict[str, Any]


@dataclass(slots=True)
class FakeBotSession(BaseSession):
    requests: list[BotApiRequest] = field(default_factory=list)
    next_message_id: int = 100

    def __post_init__(self) -> None:
        BaseSession.__init__(self)

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[TelegramType],
        timeout: int | None = None,
    ) -> TelegramType:
        del bot, timeout
        payload = method.model_dump(mode="python")
        self.requests.append(BotApiRequest(method.__api_method__, payload))
        if isinstance(method, SendMessage):
            self.next_message_id += 1
            return cast(
                TelegramType,
                Message.model_construct(
                    message_id=self.next_message_id,
                    date=datetime.now(UTC),
                    chat=Chat.model_construct(id=method.chat_id, type="private"),
                    text=method.text,
                ),
            )
        raise AssertionError(f"Unexpected Bot API method: {method.__api_method__}")

    async def close(self) -> None:
        return None

    async def stream_content(
        self,
        url: str,
        headers: dict[str, Any] | None = None,
        timeout: int = 30,
        chunk_size: int = 65536,
        raise_for_status: bool = True,
    ) -> AsyncGenerator[bytes, None]:
        del url, headers, timeout, chunk_size, raise_for_status
        if False:
            yield b""


def build_message_update(*, text: str, chat_id: int, user_id: int) -> Update:
    return Update.model_construct(
        update_id=1000,
        message=Message.model_construct(
            message_id=10,
            date=datetime.now(UTC),
            chat=Chat.model_construct(id=chat_id, type="private"),
            from_user=User.model_construct(
                id=user_id,
                is_bot=False,
                first_name="Client",
            ),
            text=text,
        ),
    )
