from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from aiogram.types import CallbackQuery

from bot.callbacks import OperatorActionCallback
from bot.handlers.operator.parsers import parse_ticket_public_id
from bot.texts.common import (
    INVALID_TICKET_ID_TEXT,
    SERVICE_UNAVAILABLE_TEXT,
    TICKET_LOCKED_TEXT,
)
from infrastructure.redis.contracts import (
    GlobalRateLimiter,
    OperatorPresenceHelper,
    TicketLockManager,
)


@asynccontextmanager
async def operator_ticket_action(
    *,
    callback: CallbackQuery,
    callback_data: OperatorActionCallback,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
    ticket_lock_manager: TicketLockManager,
) -> AsyncIterator[UUID | None]:
    ticket_public_id = parse_ticket_public_id(callback_data.ticket_public_id)
    if ticket_public_id is None:
        await respond_to_operator(callback, INVALID_TICKET_ID_TEXT)
        yield None
        return

    if not await global_rate_limiter.allow():
        await respond_to_operator(callback, SERVICE_UNAVAILABLE_TEXT)
        yield None
        return

    await operator_presence.touch(operator_id=callback.from_user.id)

    lock = ticket_lock_manager.for_ticket(callback_data.ticket_public_id)
    if not await lock.acquire():
        await respond_to_operator(callback, TICKET_LOCKED_TEXT)
        yield None
        return

    try:
        yield ticket_public_id
    finally:
        await lock.release()


async def respond_to_operator(
    callback: CallbackQuery,
    answer_text: str,
    message_text: str | None = None,
) -> None:
    await callback.answer(answer_text)
    if callback.message is not None and message_text is not None:
        await callback.message.answer(message_text)
