from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from application.contracts.runtime import GlobalRateLimiter, OperatorPresenceHelper
from application.errors import ValidationAppError
from application.use_cases.tickets.summaries import MacroManagementError
from backend.grpc.contracts import HelpdeskBackendClientFactory
from bot.adapters.helpdesk import build_request_actor
from bot.callbacks import AdminMacroCallback
from bot.handlers.admin.macro_surfaces import update_admin_source_message
from bot.handlers.admin.states import AdminMacroStates
from bot.handlers.operator.common import respond_to_operator
from bot.texts.buttons import ALL_NAVIGATION_BUTTONS, CANCEL_BUTTON_TEXT
from bot.texts.common import SERVICE_UNAVAILABLE_TEXT
from bot.texts.macros import (
    MACRO_BODY_EDIT_PROMPT_TEXT,
    MACRO_BODY_EDIT_STARTED_TEXT,
    MACRO_BODY_UPDATED_TEXT,
    MACRO_DRAFT_LOST_TEXT,
    MACRO_INPUT_COMMAND_BLOCK_TEXT,
    MACRO_INPUT_NAVIGATION_BLOCK_TEXT,
    MACRO_NOT_FOUND_TEXT,
    MACRO_TITLE_EDIT_PROMPT_TEXT,
    MACRO_TITLE_EDIT_STARTED_TEXT,
    MACRO_TITLE_UPDATED_TEXT,
)

router = Router(name="admin_macro_editing")


@router.callback_query(AdminMacroCallback.filter(F.action == "edit_title"))
async def handle_admin_macro_edit_title(
    callback: CallbackQuery,
    callback_data: AdminMacroCallback,
    state: FSMContext,
) -> None:
    await state.set_state(AdminMacroStates.editing_title)
    await state.set_data(_build_edit_state_data(callback, callback_data))
    await respond_to_operator(callback, MACRO_TITLE_EDIT_STARTED_TEXT, MACRO_TITLE_EDIT_PROMPT_TEXT)


@router.callback_query(AdminMacroCallback.filter(F.action == "edit_body"))
async def handle_admin_macro_edit_body(
    callback: CallbackQuery,
    callback_data: AdminMacroCallback,
    state: FSMContext,
) -> None:
    await state.set_state(AdminMacroStates.editing_body)
    await state.set_data(_build_edit_state_data(callback, callback_data))
    await respond_to_operator(callback, MACRO_BODY_EDIT_STARTED_TEXT, MACRO_BODY_EDIT_PROMPT_TEXT)


@router.message(StateFilter(AdminMacroStates.editing_title))
async def handle_admin_macro_edit_title_message(
    message: Message,
    state: FSMContext,
    bot: Bot,
    helpdesk_backend_client_factory: HelpdeskBackendClientFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    if await _validate_edit_input(message, MACRO_TITLE_EDIT_PROMPT_TEXT):
        return
    assert message.text is not None
    if message.from_user is None:
        return
    if not await global_rate_limiter.allow():
        await message.answer(SERVICE_UNAVAILABLE_TEXT)
        return

    await operator_presence.touch(operator_id=message.from_user.id)
    state_data = await state.get_data()
    macro_id = state_data.get("macro_id")
    page = int(state_data.get("page", 1))
    if not isinstance(macro_id, int):
        await state.clear()
        await message.answer(MACRO_DRAFT_LOST_TEXT)
        return

    try:
        async with helpdesk_backend_client_factory() as helpdesk_backend:
            macro = await helpdesk_backend.update_macro_title(
                macro_id=macro_id,
                title=message.text,
                actor=build_request_actor(message.from_user),
            )
    except (MacroManagementError, ValidationAppError) as exc:
        await message.answer(str(exc))
        return

    await state.clear()
    if macro is None:
        await message.answer(MACRO_NOT_FOUND_TEXT)
        return

    await message.answer(MACRO_TITLE_UPDATED_TEXT)
    await update_admin_source_message(
        bot=bot,
        state_data=state_data,
        macro=macro,
        page=page,
        fallback_message=message,
    )


@router.message(StateFilter(AdminMacroStates.editing_body))
async def handle_admin_macro_edit_body_message(
    message: Message,
    state: FSMContext,
    bot: Bot,
    helpdesk_backend_client_factory: HelpdeskBackendClientFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    if await _validate_edit_input(message, MACRO_BODY_EDIT_PROMPT_TEXT):
        return
    assert message.text is not None
    if message.from_user is None:
        return
    if not await global_rate_limiter.allow():
        await message.answer(SERVICE_UNAVAILABLE_TEXT)
        return

    await operator_presence.touch(operator_id=message.from_user.id)
    state_data = await state.get_data()
    macro_id = state_data.get("macro_id")
    page = int(state_data.get("page", 1))
    if not isinstance(macro_id, int):
        await state.clear()
        await message.answer(MACRO_DRAFT_LOST_TEXT)
        return

    try:
        async with helpdesk_backend_client_factory() as helpdesk_backend:
            macro = await helpdesk_backend.update_macro_body(
                macro_id=macro_id,
                body=message.text,
                actor=build_request_actor(message.from_user),
            )
    except (MacroManagementError, ValidationAppError) as exc:
        await message.answer(str(exc))
        return

    await state.clear()
    if macro is None:
        await message.answer(MACRO_NOT_FOUND_TEXT)
        return

    await message.answer(MACRO_BODY_UPDATED_TEXT)
    await update_admin_source_message(
        bot=bot,
        state_data=state_data,
        macro=macro,
        page=page,
        fallback_message=message,
    )


def _build_edit_state_data(
    callback: CallbackQuery,
    callback_data: AdminMacroCallback,
) -> dict[str, int]:
    data: dict[str, int] = {
        "macro_id": callback_data.macro_id,
        "page": callback_data.page,
    }
    if isinstance(callback.message, Message):
        data["source_chat_id"] = callback.message.chat.id
        data["source_message_id"] = callback.message.message_id
    return data


async def _validate_edit_input(message: Message, prompt_text: str) -> bool:
    if message.text is None:
        await message.answer(prompt_text)
        return True
    if message.text in ALL_NAVIGATION_BUTTONS and message.text != CANCEL_BUTTON_TEXT:
        await message.answer(MACRO_INPUT_NAVIGATION_BLOCK_TEXT)
        return True
    if message.text.startswith("/"):
        await message.answer(MACRO_INPUT_COMMAND_BLOCK_TEXT)
        return True
    return False
