from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from application.services.helpdesk.service import HelpdeskServiceFactory
from bot.formatters.operator import format_operational_stats
from bot.texts.buttons import STATS_BUTTON_TEXT
from bot.texts.common import SERVICE_UNAVAILABLE_TEXT
from infrastructure.redis.contracts import GlobalRateLimiter, OperatorPresenceHelper

router = Router(name="operator_stats")


@router.message(Command("stats"))
@router.message(F.text == STATS_BUTTON_TEXT)
async def handle_stats(
    message: Message,
    state: FSMContext,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    if not await global_rate_limiter.allow():
        await message.answer(SERVICE_UNAVAILABLE_TEXT)
        return

    if message.from_user is not None:
        await operator_presence.touch(operator_id=message.from_user.id)
    await state.clear()

    async with helpdesk_service_factory() as helpdesk_service:
        stats = await helpdesk_service.get_operational_stats(
            actor_telegram_user_id=message.from_user.id if message.from_user is not None else None
        )

    await message.answer(format_operational_stats(stats))
