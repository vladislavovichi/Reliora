from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from application.services.helpdesk.service import HelpdeskServiceFactory
from application.services.stats import AnalyticsWindow
from bot.callbacks import OperatorStatsCallback
from bot.formatters.operator_stats import (
    format_analytics_section,
)
from bot.keyboards.inline.operator_stats import build_operator_stats_markup
from bot.texts.buttons import STATS_BUTTON_TEXT
from bot.texts.common import SERVICE_UNAVAILABLE_TEXT
from bot.texts.operator import build_analytics_opened_text
from infrastructure.redis.contracts import GlobalRateLimiter, OperatorPresenceHelper

router = Router(name="operator_stats")
DEFAULT_ANALYTICS_WINDOW = AnalyticsWindow.DAYS_7


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

    operator_telegram_user_id = message.from_user.id if message.from_user is not None else None
    if operator_telegram_user_id is not None:
        await operator_presence.touch(operator_id=operator_telegram_user_id)
    await state.clear()

    async with helpdesk_service_factory() as helpdesk_service:
        snapshot = await helpdesk_service.get_analytics_snapshot(
            window=DEFAULT_ANALYTICS_WINDOW,
            actor_telegram_user_id=operator_telegram_user_id,
        )

    await message.answer(
        format_analytics_section(snapshot, section="overview"),
        reply_markup=build_operator_stats_markup(
            section="overview",
            window=DEFAULT_ANALYTICS_WINDOW,
        ),
    )


@router.callback_query(OperatorStatsCallback.filter())
async def handle_stats_navigation(
    callback: CallbackQuery,
    callback_data: OperatorStatsCallback,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    if not await global_rate_limiter.allow():
        await callback.answer(SERVICE_UNAVAILABLE_TEXT)
        return

    operator_telegram_user_id = callback.from_user.id
    await operator_presence.touch(operator_id=operator_telegram_user_id)
    window = AnalyticsWindow(callback_data.window)

    async with helpdesk_service_factory() as helpdesk_service:
        snapshot = await helpdesk_service.get_analytics_snapshot(
            window=window,
            actor_telegram_user_id=operator_telegram_user_id,
        )

    answer_text = build_analytics_opened_text(section=callback_data.section, window=window)
    if not isinstance(callback.message, Message):
        await callback.answer(answer_text)
        return

    await callback.answer(answer_text)
    await callback.message.edit_text(
        format_analytics_section(snapshot, section=callback_data.section),
        reply_markup=build_operator_stats_markup(
            section=callback_data.section,
            window=window,
        ),
    )
