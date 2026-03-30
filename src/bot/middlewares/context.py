from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject


class UpdateContextMiddleware(BaseMiddleware):
    """Minimal per-update context reserved for future FSM and service wiring."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message):
            data["event_chat_id"] = event.chat.id
            data["event_user_id"] = (
                event.from_user.id if event.from_user is not None else None
            )
        elif isinstance(event, CallbackQuery):
            data["event_chat_id"] = (
                event.message.chat.id if event.message is not None else None
            )
            data["event_user_id"] = event.from_user.id

        return await handler(event, data)
