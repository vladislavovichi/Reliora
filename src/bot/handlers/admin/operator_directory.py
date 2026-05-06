from __future__ import annotations

from collections.abc import Sequence

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from application.contracts.runtime import GlobalRateLimiter, OperatorPresenceHelper
from application.use_cases.tickets.summaries import OperatorSummary
from backend.grpc.contracts import HelpdeskBackendClientFactory
from bot.adapters.helpdesk import build_request_actor
from bot.callbacks import AdminOperatorCallback
from bot.formatters.operator_admin_views import (
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

router = Router(name="admin_operator_directory")


@router.message(F.text == OPERATORS_BUTTON_TEXT)
async def handle_operators(
    message: Message,
    state: FSMContext,
    settings: Settings,
    helpdesk_backend_client_factory: HelpdeskBackendClientFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    if not await global_rate_limiter.allow():
        await message.answer(SERVICE_UNAVAILABLE_TEXT)
        return
    if message.from_user is not None:
        await operator_presence.touch(operator_id=message.from_user.id)
    await state.clear()

    async with helpdesk_backend_client_factory() as helpdesk_backend:
        operators = await helpdesk_backend.list_operators(
            actor=build_request_actor(message.from_user)
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
    helpdesk_backend_client_factory: HelpdeskBackendClientFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    if not await global_rate_limiter.allow():
        await respond_to_operator(callback, SERVICE_UNAVAILABLE_TEXT)
        return

    await operator_presence.touch(operator_id=callback.from_user.id)
    await state.clear()

    async with helpdesk_backend_client_factory() as helpdesk_backend:
        operators = await helpdesk_backend.list_operators(
            actor=build_request_actor(callback.from_user)
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
    settings: Settings,
    helpdesk_backend_client_factory: HelpdeskBackendClientFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    if not await global_rate_limiter.allow():
        await respond_to_operator(callback, SERVICE_UNAVAILABLE_TEXT)
        return

    await operator_presence.touch(operator_id=callback.from_user.id)
    await state.clear()

    async with helpdesk_backend_client_factory() as helpdesk_backend:
        operators = await helpdesk_backend.list_operators(
            actor=build_request_actor(callback.from_user)
        )

    operator = next(
        (item for item in operators if item.telegram_user_id == callback_data.telegram_user_id),
        None,
    )
    if operator is None:
        await _edit_operator_list(
            callback=callback,
            operators=operators,
            settings=settings,
            answer_text=OPERATORS_REFRESHED_TEXT,
        )
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
    helpdesk_backend_client_factory: HelpdeskBackendClientFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    if not await global_rate_limiter.allow():
        await respond_to_operator(callback, SERVICE_UNAVAILABLE_TEXT)
        return

    await operator_presence.touch(operator_id=callback.from_user.id)
    await state.clear()

    async with helpdesk_backend_client_factory() as helpdesk_backend:
        operators = await helpdesk_backend.list_operators(
            actor=build_request_actor(callback.from_user)
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
