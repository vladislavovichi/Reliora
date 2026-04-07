from __future__ import annotations

from collections.abc import Sequence

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from application.services.helpdesk.service import HelpdeskServiceFactory
from application.use_cases.tickets.summaries import OperatorSummary
from bot.callbacks import AdminOperatorCallback
from bot.formatters.operator import (
    format_operator_detail_response,
    format_operator_list_response,
)
from bot.handlers.operator.common import respond_to_operator
from bot.keyboards.inline.admin import (
    build_operator_detail_markup,
    build_operator_management_markup,
)
from bot.texts.buttons import OPERATORS_BUTTON_TEXT
from bot.texts.common import SERVICE_UNAVAILABLE_TEXT
from bot.texts.operator import OPERATORS_REFRESHED_TEXT
from infrastructure.config.settings import Settings
from infrastructure.redis.contracts import GlobalRateLimiter, OperatorPresenceHelper

router = Router(name="admin_operator_directory")


@router.message(Command("operators"))
@router.message(F.text == OPERATORS_BUTTON_TEXT)
async def handle_operators(
    message: Message,
    state: FSMContext,
    settings: Settings,
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
        operators = await helpdesk_service.list_operators(
            actor_telegram_user_id=message.from_user.id if message.from_user is not None else None
        )

    await message.answer(
        _build_operator_list_text(operators=operators, settings=settings),
        reply_markup=build_operator_management_markup(operators=operators),
    )


@router.callback_query(AdminOperatorCallback.filter(F.action == "refresh"))
async def handle_refresh_operators(
    callback: CallbackQuery,
    state: FSMContext,
    settings: Settings,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    if not await global_rate_limiter.allow():
        await respond_to_operator(callback, SERVICE_UNAVAILABLE_TEXT)
        return

    await operator_presence.touch(operator_id=callback.from_user.id)
    await state.clear()

    async with helpdesk_service_factory() as helpdesk_service:
        operators = await helpdesk_service.list_operators(
            actor_telegram_user_id=callback.from_user.id
        )

    await _edit_operator_list(
        callback=callback,
        operators=operators,
        settings=settings,
        answer_text=OPERATORS_REFRESHED_TEXT,
    )


@router.callback_query(AdminOperatorCallback.filter(F.action == "view"))
async def handle_operator_view(
    callback: CallbackQuery,
    callback_data: AdminOperatorCallback,
    state: FSMContext,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    if not await global_rate_limiter.allow():
        await respond_to_operator(callback, SERVICE_UNAVAILABLE_TEXT)
        return

    await operator_presence.touch(operator_id=callback.from_user.id)
    await state.clear()

    async with helpdesk_service_factory() as helpdesk_service:
        operators = await helpdesk_service.list_operators(
            actor_telegram_user_id=callback.from_user.id
        )

    operator = next(
        (
            item
            for item in operators
            if item.telegram_user_id == callback_data.telegram_user_id
        ),
        None,
    )
    if operator is None:
        await respond_to_operator(callback, OPERATORS_REFRESHED_TEXT)
        return
    if not isinstance(callback.message, Message):
        await callback.answer(operator.display_name)
        return

    await callback.answer(operator.display_name)
    await callback.message.edit_text(
        format_operator_detail_response(operator),
        reply_markup=build_operator_detail_markup(
            telegram_user_id=operator.telegram_user_id,
        ),
    )


@router.callback_query(AdminOperatorCallback.filter(F.action == "back_list"))
async def handle_back_to_operator_list(
    callback: CallbackQuery,
    state: FSMContext,
    settings: Settings,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    if not await global_rate_limiter.allow():
        await respond_to_operator(callback, SERVICE_UNAVAILABLE_TEXT)
        return

    await operator_presence.touch(operator_id=callback.from_user.id)
    await state.clear()

    async with helpdesk_service_factory() as helpdesk_service:
        operators = await helpdesk_service.list_operators(
            actor_telegram_user_id=callback.from_user.id
        )

    await _edit_operator_list(
        callback=callback,
        operators=operators,
        settings=settings,
        answer_text=OPERATORS_REFRESHED_TEXT,
    )


def _build_operator_list_text(
    *,
    operators: Sequence[OperatorSummary],
    settings: Settings,
) -> str:
    return format_operator_list_response(
        operators=operators,
        super_admin_telegram_user_ids=settings.authorization.super_admin_telegram_user_ids,
    )


async def _edit_operator_list(
    *,
    callback: CallbackQuery,
    operators: Sequence[OperatorSummary],
    settings: Settings,
    answer_text: str,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer(answer_text)
        return

    await callback.answer(answer_text)
    await callback.message.edit_text(
        _build_operator_list_text(operators=operators, settings=settings),
        reply_markup=build_operator_management_markup(operators=operators),
    )
