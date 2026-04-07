from __future__ import annotations

import logging
from collections.abc import Sequence

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from application.services.helpdesk.service import HelpdeskServiceFactory
from application.use_cases.tickets.summaries import OperatorManagementError, OperatorSummary
from bot.callbacks import AdminOperatorCallback
from bot.formatters.operator import format_operator_detail_response, format_operator_list_response
from bot.handlers.admin.states import AdminOperatorStates
from bot.handlers.operator.common import respond_to_operator
from bot.handlers.operator.parsers import parse_operator_argument_with_optional_name
from bot.keyboards.inline.admin import (
    build_operator_detail_markup,
    build_operator_management_markup,
    build_operator_revoke_confirmation_markup,
)
from bot.texts.buttons import ALL_NAVIGATION_BUTTONS, CANCEL_BUTTON_TEXT
from bot.texts.common import SERVICE_UNAVAILABLE_TEXT
from bot.texts.operator import (
    OPERATOR_ADD_INVALID_TEXT,
    OPERATOR_ADD_PROMPT_TEXT,
    OPERATOR_ADD_STARTED_TEXT,
    OPERATOR_INPUT_NAVIGATION_BLOCK_TEXT,
    OPERATORS_EMPTY_TEXT,
    REVOKE_CANCELLED_TEXT,
    REVOKE_CONFIRM_PROMPT_TEXT,
    build_promote_operator_result_text,
    build_revoke_confirm_message,
    build_revoke_operator_result_text,
)
from infrastructure.config.settings import Settings
from infrastructure.redis.contracts import GlobalRateLimiter, OperatorPresenceHelper

router = Router(name="admin_operator_mutations")
logger = logging.getLogger(__name__)


@router.callback_query(AdminOperatorCallback.filter(F.action == "add"))
async def handle_add_operator_start(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.set_state(AdminOperatorStates.adding_operator)
    await callback.answer(OPERATOR_ADD_STARTED_TEXT)
    if isinstance(callback.message, Message):
        await callback.message.answer(OPERATOR_ADD_PROMPT_TEXT)


@router.message(StateFilter(AdminOperatorStates.adding_operator), F.text)
async def handle_add_operator_message(
    message: Message,
    state: FSMContext,
    settings: Settings,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    if message.text is None:
        await message.answer(OPERATOR_ADD_PROMPT_TEXT)
        return
    if message.text in ALL_NAVIGATION_BUTTONS and message.text != CANCEL_BUTTON_TEXT:
        await message.answer(OPERATOR_INPUT_NAVIGATION_BLOCK_TEXT)
        return
    if message.text.startswith("/"):
        await message.answer(OPERATOR_ADD_PROMPT_TEXT)
        return

    parsed = parse_operator_argument_with_optional_name(message.text)
    if parsed is None:
        await message.answer(OPERATOR_ADD_INVALID_TEXT)
        return
    if not await global_rate_limiter.allow():
        await message.answer(SERVICE_UNAVAILABLE_TEXT)
        return
    if message.from_user is None:
        return

    await operator_presence.touch(operator_id=message.from_user.id)
    telegram_user_id, display_name = parsed

    async with helpdesk_service_factory() as helpdesk_service:
        try:
            result = await helpdesk_service.promote_operator(
                telegram_user_id=telegram_user_id,
                display_name=display_name,
                actor_telegram_user_id=message.from_user.id,
            )
        except OperatorManagementError as exc:
            await message.answer(str(exc))
            return

        operators = await helpdesk_service.list_operators(
            actor_telegram_user_id=message.from_user.id,
        )

    await state.clear()
    logger.info(
        "Operator promoted actor_id=%s target_id=%s changed=%s",
        message.from_user.id,
        result.operator.telegram_user_id,
        result.changed,
    )
    await message.answer(
        build_promote_operator_result_text(
            result.operator.display_name,
            result.operator.telegram_user_id,
            changed=result.changed,
        )
    )
    await message.answer(
        _build_operator_list_text(operators=operators, settings=settings),
        reply_markup=build_operator_management_markup(operators=operators),
    )


@router.callback_query(AdminOperatorCallback.filter(F.action == "revoke"))
async def handle_revoke_operator_prompt(
    callback: CallbackQuery,
    callback_data: AdminOperatorCallback,
) -> None:
    await callback.answer(REVOKE_CONFIRM_PROMPT_TEXT)
    if not isinstance(callback.message, Message):
        return

    await callback.message.edit_text(
        build_revoke_confirm_message(callback_data.telegram_user_id),
        reply_markup=build_operator_revoke_confirmation_markup(
            telegram_user_id=callback_data.telegram_user_id
        ),
    )


@router.callback_query(AdminOperatorCallback.filter(F.action == "confirm_revoke"))
async def handle_confirm_revoke_operator(
    callback: CallbackQuery,
    callback_data: AdminOperatorCallback,
    settings: Settings,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    if not await global_rate_limiter.allow():
        await respond_to_operator(callback, SERVICE_UNAVAILABLE_TEXT)
        return

    await operator_presence.touch(operator_id=callback.from_user.id)

    async with helpdesk_service_factory() as helpdesk_service:
        try:
            result = await helpdesk_service.revoke_operator(
                telegram_user_id=callback_data.telegram_user_id,
                actor_telegram_user_id=callback.from_user.id,
            )
        except OperatorManagementError as exc:
            await respond_to_operator(callback, str(exc))
            return

        operators = await helpdesk_service.list_operators(
            actor_telegram_user_id=callback.from_user.id
        )

    answer_text = (
        OPERATORS_EMPTY_TEXT
        if result is None
        else build_revoke_operator_result_text(
            result.operator.display_name,
            result.operator.telegram_user_id,
        )
    )
    if result is not None:
        logger.info(
            "Operator revoked actor_id=%s target_id=%s",
            callback.from_user.id,
            result.operator.telegram_user_id,
        )

    await callback.answer(answer_text)
    if not isinstance(callback.message, Message):
        return

    await callback.message.edit_text(
        _build_operator_list_text(operators=operators, settings=settings),
        reply_markup=build_operator_management_markup(operators=operators),
    )


@router.callback_query(AdminOperatorCallback.filter(F.action == "cancel_revoke"))
async def handle_cancel_revoke_operator(
    callback: CallbackQuery,
    callback_data: AdminOperatorCallback,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    if not await global_rate_limiter.allow():
        await respond_to_operator(callback, SERVICE_UNAVAILABLE_TEXT)
        return

    await operator_presence.touch(operator_id=callback.from_user.id)
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
    await callback.answer(REVOKE_CANCELLED_TEXT)
    if isinstance(callback.message, Message) and operator is not None:
        await callback.message.edit_text(
            format_operator_detail_response(operator),
            reply_markup=build_operator_detail_markup(
                telegram_user_id=operator.telegram_user_id,
            ),
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
