from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from application.services.helpdesk.service import HelpdeskServiceFactory
from application.use_cases.tickets.summaries import CategoryManagementError
from bot.callbacks import AdminCategoryCallback
from bot.formatters.categories import format_admin_category_details
from bot.handlers.admin.category_surfaces import (
    build_admin_category_list_response,
    update_admin_category_source_message,
)
from bot.handlers.admin.states import AdminCategoryStates
from bot.handlers.operator.common import respond_to_operator
from bot.texts.buttons import ALL_NAVIGATION_BUTTONS, CANCEL_BUTTON_TEXT
from bot.texts.categories import (
    CATEGORY_CREATE_SAVED_TEXT,
    CATEGORY_CREATE_STARTED_TEXT,
    CATEGORY_CREATE_TITLE_PROMPT_TEXT,
    CATEGORY_DRAFT_LOST_TEXT,
    CATEGORY_EDIT_STARTED_TEXT,
    CATEGORY_EDIT_TITLE_PROMPT_TEXT,
    CATEGORY_INPUT_COMMAND_BLOCK_TEXT,
    CATEGORY_INPUT_NAVIGATION_BLOCK_TEXT,
    CATEGORY_NOT_FOUND_TEXT,
    CATEGORY_TITLE_UPDATED_TEXT,
)
from bot.texts.common import SERVICE_UNAVAILABLE_TEXT
from infrastructure.redis.contracts import GlobalRateLimiter, OperatorPresenceHelper

router = Router(name="admin_category_mutations")


@router.callback_query(AdminCategoryCallback.filter(F.action == "create"))
async def handle_admin_category_create(
    callback: CallbackQuery,
    callback_data: AdminCategoryCallback,
    state: FSMContext,
) -> None:
    await state.set_state(AdminCategoryStates.creating_title)
    await state.set_data({"page": callback_data.page})
    await respond_to_operator(
        callback,
        CATEGORY_CREATE_STARTED_TEXT,
        CATEGORY_CREATE_TITLE_PROMPT_TEXT,
    )


@router.callback_query(AdminCategoryCallback.filter(F.action == "edit_title"))
async def handle_admin_category_edit_title(
    callback: CallbackQuery,
    callback_data: AdminCategoryCallback,
    state: FSMContext,
) -> None:
    await state.set_state(AdminCategoryStates.editing_title)
    await state.set_data(_build_edit_state_data(callback, callback_data))
    await respond_to_operator(
        callback,
        CATEGORY_EDIT_STARTED_TEXT,
        CATEGORY_EDIT_TITLE_PROMPT_TEXT,
    )


@router.message(StateFilter(AdminCategoryStates.creating_title))
async def handle_admin_category_create_title(
    message: Message,
    state: FSMContext,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    if await _validate_category_input(message, CATEGORY_CREATE_TITLE_PROMPT_TEXT):
        return
    assert message.text is not None
    if message.from_user is None:
        return
    if not await global_rate_limiter.allow():
        await message.answer(SERVICE_UNAVAILABLE_TEXT)
        return

    await operator_presence.touch(operator_id=message.from_user.id)
    page = int((await state.get_data()).get("page", 1))
    try:
        async with helpdesk_service_factory() as helpdesk_service:
            category = await helpdesk_service.create_ticket_category(
                title=message.text,
                actor_telegram_user_id=message.from_user.id,
            )
    except CategoryManagementError as exc:
        await message.answer(str(exc))
        return

    await state.clear()
    await message.answer(CATEGORY_CREATE_SAVED_TEXT)
    await message.answer(format_admin_category_details(category))
    async with helpdesk_service_factory() as helpdesk_service:
        categories = await helpdesk_service.list_ticket_categories(
            actor_telegram_user_id=message.from_user.id
        )
    text, markup = build_admin_category_list_response(categories=categories, page=page)
    await message.answer(text, reply_markup=markup)


@router.message(StateFilter(AdminCategoryStates.editing_title))
async def handle_admin_category_edit_title_message(
    message: Message,
    state: FSMContext,
    bot: Bot,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    if await _validate_category_input(message, CATEGORY_EDIT_TITLE_PROMPT_TEXT):
        return
    assert message.text is not None
    if message.from_user is None:
        return
    if not await global_rate_limiter.allow():
        await message.answer(SERVICE_UNAVAILABLE_TEXT)
        return

    await operator_presence.touch(operator_id=message.from_user.id)
    state_data = await state.get_data()
    category_id = state_data.get("category_id")
    page = int(state_data.get("page", 1))
    if not isinstance(category_id, int):
        await state.clear()
        await message.answer(CATEGORY_DRAFT_LOST_TEXT)
        return

    try:
        async with helpdesk_service_factory() as helpdesk_service:
            category = await helpdesk_service.update_ticket_category_title(
                category_id=category_id,
                title=message.text,
                actor_telegram_user_id=message.from_user.id,
            )
    except CategoryManagementError as exc:
        await message.answer(str(exc))
        return

    await state.clear()
    if category is None:
        await message.answer(CATEGORY_NOT_FOUND_TEXT)
        return

    await message.answer(CATEGORY_TITLE_UPDATED_TEXT)
    await update_admin_category_source_message(
        bot=bot,
        state_data=state_data,
        category=category,
        page=page,
        fallback_message=message,
    )


def _build_edit_state_data(
    callback: CallbackQuery,
    callback_data: AdminCategoryCallback,
) -> dict[str, int]:
    data: dict[str, int] = {
        "category_id": callback_data.category_id,
        "page": callback_data.page,
    }
    if isinstance(callback.message, Message):
        data["source_chat_id"] = callback.message.chat.id
        data["source_message_id"] = callback.message.message_id
    return data


async def _validate_category_input(message: Message, prompt_text: str) -> bool:
    if message.text is None:
        await message.answer(prompt_text)
        return True
    if message.text in ALL_NAVIGATION_BUTTONS and message.text != CANCEL_BUTTON_TEXT:
        await message.answer(CATEGORY_INPUT_NAVIGATION_BLOCK_TEXT)
        return True
    if message.text.startswith("/"):
        await message.answer(CATEGORY_INPUT_COMMAND_BLOCK_TEXT)
        return True
    return False
