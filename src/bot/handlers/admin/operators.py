from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message

from application.services.helpdesk import HelpdeskServiceFactory
from application.use_cases.tickets import OperatorManagementError
from bot.callbacks import AdminOperatorCallback
from bot.formatters.operator import format_operator_list_response
from bot.handlers.operator.common import respond_to_operator
from bot.handlers.operator.parsers import (
    parse_operator_argument_with_optional_name,
    parse_telegram_user_id,
)
from bot.keyboards.inline.admin import (
    build_operator_management_markup,
    build_operator_revoke_confirmation_markup,
)
from bot.texts.buttons import (
    ADD_OPERATOR_BUTTON_TEXT,
    OPERATORS_BUTTON_TEXT,
    REMOVE_OPERATOR_BUTTON_TEXT,
)
from bot.texts.common import SERVICE_UNAVAILABLE_TEXT
from bot.texts.operator import (
    OPERATORS_EMPTY_TEXT,
    OPERATORS_REFRESHED_TEXT,
    REVOKE_CANCELLED_TEXT,
    REVOKE_CONFIRM_PROMPT_TEXT,
    add_operator_guidance,
    build_promote_operator_result_text,
    build_revoke_confirm_message,
    build_revoke_operator_result_text,
    invalid_add_operator_usage_text,
    invalid_remove_operator_usage_text,
    remove_operator_guidance,
)
from infrastructure.config import Settings
from infrastructure.redis.contracts import GlobalRateLimiter, OperatorPresenceHelper

router = Router(name="admin_operators")


@router.message(Command("operators"))
@router.message(F.text == OPERATORS_BUTTON_TEXT)
async def handle_operators(
    message: Message,
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

    async with helpdesk_service_factory() as helpdesk_service:
        operators = await helpdesk_service.list_operators(
            actor_telegram_user_id=message.from_user.id if message.from_user is not None else None
        )

    await message.answer(
        format_operator_list_response(
            operators=operators,
            super_admin_telegram_user_ids=settings.authorization.super_admin_telegram_user_ids,
        ),
        reply_markup=build_operator_management_markup(operators=operators),
    )


@router.message(F.text == ADD_OPERATOR_BUTTON_TEXT)
async def handle_add_operator_button(message: Message) -> None:
    await message.answer(add_operator_guidance())


@router.message(F.text == REMOVE_OPERATOR_BUTTON_TEXT)
async def handle_remove_operator_button(message: Message) -> None:
    await message.answer(remove_operator_guidance())


@router.message(Command("add_operator"))
async def handle_add_operator(
    message: Message,
    command: CommandObject,
    settings: Settings,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    parsed = parse_operator_argument_with_optional_name(command.args)
    if parsed is None:
        await message.answer(invalid_add_operator_usage_text())
        return

    telegram_user_id, display_name = parsed
    if not await global_rate_limiter.allow():
        await message.answer(SERVICE_UNAVAILABLE_TEXT)
        return

    if message.from_user is not None:
        await operator_presence.touch(operator_id=message.from_user.id)

    actor_telegram_user_id = message.from_user.id if message.from_user is not None else None
    async with helpdesk_service_factory() as helpdesk_service:
        try:
            result = await helpdesk_service.promote_operator(
                telegram_user_id=telegram_user_id,
                display_name=display_name,
                actor_telegram_user_id=actor_telegram_user_id,
            )
        except OperatorManagementError as exc:
            await message.answer(str(exc))
            return

        operators = await helpdesk_service.list_operators(
            actor_telegram_user_id=actor_telegram_user_id
        )

    await message.answer(
        build_promote_operator_result_text(
            result.operator.display_name,
            result.operator.telegram_user_id,
            changed=result.changed,
        )
    )
    await message.answer(
        format_operator_list_response(
            operators=operators,
            super_admin_telegram_user_ids=settings.authorization.super_admin_telegram_user_ids,
        ),
        reply_markup=build_operator_management_markup(operators=operators),
    )


@router.message(Command("remove_operator"))
async def handle_remove_operator(
    message: Message,
    command: CommandObject,
    settings: Settings,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    telegram_user_id = parse_telegram_user_id(command.args)
    if telegram_user_id is None:
        await message.answer(invalid_remove_operator_usage_text())
        return

    if not await global_rate_limiter.allow():
        await message.answer(SERVICE_UNAVAILABLE_TEXT)
        return

    if message.from_user is not None:
        await operator_presence.touch(operator_id=message.from_user.id)

    actor_telegram_user_id = message.from_user.id if message.from_user is not None else None
    async with helpdesk_service_factory() as helpdesk_service:
        try:
            result = await helpdesk_service.revoke_operator(
                telegram_user_id=telegram_user_id,
                actor_telegram_user_id=actor_telegram_user_id,
            )
        except OperatorManagementError as exc:
            await message.answer(str(exc))
            return

        operators = await helpdesk_service.list_operators(
            actor_telegram_user_id=actor_telegram_user_id
        )

    if result is None:
        await message.answer(OPERATORS_EMPTY_TEXT)
    else:
        await message.answer(
            build_revoke_operator_result_text(
                result.operator.display_name,
                result.operator.telegram_user_id,
            )
        )

    await message.answer(
        format_operator_list_response(
            operators=operators,
            super_admin_telegram_user_ids=settings.authorization.super_admin_telegram_user_ids,
        ),
        reply_markup=build_operator_management_markup(operators=operators),
    )


@router.callback_query(AdminOperatorCallback.filter(F.action == "refresh"))
async def handle_refresh_operators(
    callback: CallbackQuery,
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
        operators = await helpdesk_service.list_operators(
            actor_telegram_user_id=callback.from_user.id
        )

    await callback.answer(OPERATORS_REFRESHED_TEXT)
    if callback.message is not None:
        await callback.message.answer(
            format_operator_list_response(
                operators=operators,
                super_admin_telegram_user_ids=settings.authorization.super_admin_telegram_user_ids,
            ),
            reply_markup=build_operator_management_markup(operators=operators),
        )


@router.callback_query(AdminOperatorCallback.filter(F.action == "revoke"))
async def handle_revoke_operator_prompt(
    callback: CallbackQuery,
    callback_data: AdminOperatorCallback,
) -> None:
    await callback.answer(REVOKE_CONFIRM_PROMPT_TEXT)
    if callback.message is not None:
        await callback.message.answer(
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

    await callback.answer(answer_text)
    if callback.message is not None:
        await callback.message.answer(
            format_operator_list_response(
                operators=operators,
                super_admin_telegram_user_ids=settings.authorization.super_admin_telegram_user_ids,
            ),
            reply_markup=build_operator_management_markup(operators=operators),
        )


@router.callback_query(AdminOperatorCallback.filter(F.action == "cancel_revoke"))
async def handle_cancel_revoke_operator(callback: CallbackQuery) -> None:
    await callback.answer(REVOKE_CANCELLED_TEXT)
    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(reply_markup=None)
