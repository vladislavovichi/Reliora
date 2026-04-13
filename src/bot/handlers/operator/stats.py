from __future__ import annotations

import logging

import grpc
from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from application.services.stats import AnalyticsWindow, get_analytics_window_label
from application.use_cases.analytics.exports import (
    AnalyticsExportFormat,
    AnalyticsSection,
    get_analytics_section_label,
)
from backend.grpc.contracts import HelpdeskBackendClientFactory
from bot.adapters.helpdesk import build_request_actor, build_request_actor_from_id
from bot.callbacks import OperatorStatsCallback, OperatorStatsExportCallback
from bot.delivery import deliver_document_to_chat
from bot.formatters.operator_stats import (
    format_analytics_export_actions,
    format_analytics_section,
)
from bot.keyboards.inline.operator_stats import (
    build_operator_stats_export_markup,
    build_operator_stats_markup,
)
from bot.texts.buttons import STATS_BUTTON_TEXT
from bot.texts.common import SERVICE_UNAVAILABLE_TEXT
from bot.texts.operator import (
    ANALYTICS_EXPORT_DELIVERY_FAILED_TEXT,
    ANALYTICS_EXPORT_FAILED_TEXT,
    build_analytics_export_opened_text,
    build_analytics_export_ready_text,
    build_analytics_opened_text,
)
from domain.tickets import InvalidTicketTransitionError
from infrastructure.redis.contracts import GlobalRateLimiter, OperatorPresenceHelper

router = Router(name="operator_stats")
DEFAULT_ANALYTICS_WINDOW = AnalyticsWindow.DAYS_7
logger = logging.getLogger(__name__)


@router.message(F.text == STATS_BUTTON_TEXT)
async def handle_stats(
    message: Message,
    state: FSMContext,
    helpdesk_backend_client_factory: HelpdeskBackendClientFactory,
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

    async with helpdesk_backend_client_factory() as helpdesk_backend:
        snapshot = await helpdesk_backend.get_analytics_snapshot(
            window=DEFAULT_ANALYTICS_WINDOW,
            actor=build_request_actor_from_id(operator_telegram_user_id),
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
    helpdesk_backend_client_factory: HelpdeskBackendClientFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    if not await global_rate_limiter.allow():
        await callback.answer(SERVICE_UNAVAILABLE_TEXT)
        return

    operator_telegram_user_id = callback.from_user.id
    await operator_presence.touch(operator_id=operator_telegram_user_id)
    window = AnalyticsWindow(callback_data.window)

    async with helpdesk_backend_client_factory() as helpdesk_backend:
        snapshot = await helpdesk_backend.get_analytics_snapshot(
            window=window,
            actor=build_request_actor(callback.from_user),
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


@router.callback_query(OperatorStatsExportCallback.filter(F.action == "open"))
async def handle_stats_export_menu(
    callback: CallbackQuery,
    callback_data: OperatorStatsExportCallback,
    helpdesk_backend_client_factory: HelpdeskBackendClientFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    if not await global_rate_limiter.allow():
        await callback.answer(SERVICE_UNAVAILABLE_TEXT)
        return

    await operator_presence.touch(operator_id=callback.from_user.id)
    window = AnalyticsWindow(callback_data.window)
    section = callback_data.section

    async with helpdesk_backend_client_factory() as helpdesk_backend:
        snapshot = await helpdesk_backend.get_analytics_snapshot(
            window=window,
            actor=build_request_actor(callback.from_user),
        )

    answer_text = build_analytics_export_opened_text(section=section, window=window)
    if not isinstance(callback.message, Message):
        await callback.answer(answer_text)
        return

    await callback.answer(answer_text)
    await callback.message.edit_text(
        format_analytics_export_actions(snapshot, section=section),
        reply_markup=build_operator_stats_export_markup(section=section, window=window),
    )


@router.callback_query(OperatorStatsExportCallback.filter(F.action.in_({"csv", "html"})))
async def handle_stats_export_file(
    callback: CallbackQuery,
    callback_data: OperatorStatsExportCallback,
    bot: Bot,
    helpdesk_backend_client_factory: HelpdeskBackendClientFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    if not await global_rate_limiter.allow():
        await callback.answer(SERVICE_UNAVAILABLE_TEXT)
        return

    await operator_presence.touch(operator_id=callback.from_user.id)
    window = AnalyticsWindow(callback_data.window)
    section = AnalyticsSection(callback_data.section)
    export_format = (
        AnalyticsExportFormat.CSV if callback_data.action == "csv" else AnalyticsExportFormat.HTML
    )

    try:
        async with helpdesk_backend_client_factory() as helpdesk_backend:
            export = await helpdesk_backend.export_analytics_snapshot(
                window=window,
                section=section,
                format=export_format,
                actor=build_request_actor(callback.from_user),
            )
    except (
        grpc.aio.AioRpcError,
        InvalidTicketTransitionError,
        PermissionError,
        ValueError,
        RuntimeError,
        TimeoutError,
        OSError,
    ):
        logger.exception(
            "Analytics export failed operator_id=%s section=%s window=%s format=%s",
            callback.from_user.id,
            section.value,
            window.value,
            export_format.value,
        )
        await callback.answer(ANALYTICS_EXPORT_FAILED_TEXT, show_alert=True)
        return

    delivery_error = await deliver_document_to_chat(
        bot,
        chat_id=callback.from_user.id,
        content=export.content,
        filename=export.filename,
        caption=(
            f"Аналитика · {get_analytics_section_label(section)} · "
            f"{get_analytics_window_label(window)}"
        ),
        logger=logger,
        operation=f"analytics_export_{export_format.value}",
    )
    if delivery_error is not None:
        logger.warning(
            (
                "Analytics export delivery failed operator_id=%s section=%s "
                "window=%s format=%s error=%s"
            ),
            callback.from_user.id,
            section.value,
            window.value,
            export_format.value,
            delivery_error,
        )
        await callback.answer(ANALYTICS_EXPORT_DELIVERY_FAILED_TEXT, show_alert=True)
        return

    await callback.answer(
        build_analytics_export_ready_text(
            section=section.value,
            format_name=export_format.value.upper(),
        )
    )
