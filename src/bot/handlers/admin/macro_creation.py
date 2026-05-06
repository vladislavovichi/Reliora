from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from application.errors import ValidationAppError
from application.use_cases.tickets.summaries import MacroManagementError
from backend.grpc.contracts import HelpdeskBackendClientFactory
from bot.adapters.helpdesk import build_request_actor
from bot.callbacks import AdminMacroCallback
from bot.formatters.macros import format_admin_macro_create_preview, format_admin_macro_details
from bot.handlers.admin.macro_surfaces import edit_admin_macro_list
from bot.handlers.admin.states import AdminMacroStates
from bot.handlers.operator.common import respond_to_operator
from bot.keyboards.inline.macros import (
    build_admin_macro_create_preview_markup,
    build_admin_macro_detail_markup,
)
from bot.texts.buttons import ALL_NAVIGATION_BUTTONS, CANCEL_BUTTON_TEXT
from bot.texts.common import SERVICE_UNAVAILABLE_TEXT
from bot.texts.macros import (
    MACRO_CREATE_BODY_PROMPT_TEXT,
    MACRO_CREATE_CANCELLED_TEXT,
    MACRO_CREATE_EDIT_TEXT,
    MACRO_CREATE_SAVED_TEXT,
    MACRO_CREATE_STARTED_TEXT,
    MACRO_CREATE_TITLE_PROMPT_TEXT,
    MACRO_DRAFT_LOST_TEXT,
    MACRO_INPUT_COMMAND_BLOCK_TEXT,
    MACRO_INPUT_NAVIGATION_BLOCK_TEXT,
    MACRO_PREVIEW_COMMAND_BLOCK_TEXT,
)
from infrastructure.redis.contracts import GlobalRateLimiter, OperatorPresenceHelper

router = Router(name="admin_macro_creation")


@router.callback_query(AdminMacroCallback.filter(F.action == "create"))
async def handle_admin_macro_create(
    callback: CallbackQuery,
    callback_data: AdminMacroCallback,
    state: FSMContext,
) -> None:
    await state.set_state(AdminMacroStates.creating_title)
    await state.set_data({"page": callback_data.page})
    await respond_to_operator(
        callback,
        MACRO_CREATE_STARTED_TEXT,
        MACRO_CREATE_TITLE_PROMPT_TEXT,
    )


@router.callback_query(AdminMacroCallback.filter(F.action == "preview_save"))
async def handle_admin_macro_preview_save(
    callback: CallbackQuery,
    callback_data: AdminMacroCallback,
    state: FSMContext,
    helpdesk_backend_client_factory: HelpdeskBackendClientFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    if not await global_rate_limiter.allow():
        await respond_to_operator(callback, SERVICE_UNAVAILABLE_TEXT)
        return

    await operator_presence.touch(operator_id=callback.from_user.id)
    state_data = await state.get_data()
    title = state_data.get("draft_title")
    body = state_data.get("draft_body")
    if not isinstance(title, str) or not isinstance(body, str):
        await state.clear()
        await respond_to_operator(callback, MACRO_DRAFT_LOST_TEXT)
        return

    try:
        async with helpdesk_backend_client_factory() as helpdesk_backend:
            macro = await helpdesk_backend.create_macro(
                title=title,
                body=body,
                actor=build_request_actor(callback.from_user),
            )
    except (MacroManagementError, ValidationAppError) as exc:
        await respond_to_operator(callback, str(exc))
        return

    await state.clear()
    if not isinstance(callback.message, Message):
        await callback.answer(MACRO_CREATE_SAVED_TEXT)
        return

    await callback.answer(MACRO_CREATE_SAVED_TEXT)
    await callback.message.edit_text(
        format_admin_macro_details(macro),
        reply_markup=build_admin_macro_detail_markup(
            macro_id=macro.id,
            page=callback_data.page,
        ),
    )


@router.callback_query(AdminMacroCallback.filter(F.action == "preview_edit"))
async def handle_admin_macro_preview_edit(
    callback: CallbackQuery,
    callback_data: AdminMacroCallback,
    state: FSMContext,
) -> None:
    await state.set_state(AdminMacroStates.creating_title)
    await state.update_data(page=callback_data.page)
    await respond_to_operator(callback, MACRO_CREATE_EDIT_TEXT, MACRO_CREATE_TITLE_PROMPT_TEXT)


@router.callback_query(AdminMacroCallback.filter(F.action == "preview_cancel"))
async def handle_admin_macro_preview_cancel(
    callback: CallbackQuery,
    callback_data: AdminMacroCallback,
    state: FSMContext,
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
        macros = await helpdesk_backend.list_macros(actor=build_request_actor(callback.from_user))

    await edit_admin_macro_list(
        callback=callback,
        macros=macros,
        page=callback_data.page,
        answer_text=MACRO_CREATE_CANCELLED_TEXT,
    )


@router.message(StateFilter(AdminMacroStates.creating_title))
async def handle_admin_macro_create_title(
    message: Message,
    state: FSMContext,
) -> None:
    if await _validate_create_input(message, MACRO_CREATE_TITLE_PROMPT_TEXT):
        return
    assert message.text is not None

    await state.set_state(AdminMacroStates.creating_body)
    await state.update_data(draft_title=message.text)
    await message.answer(MACRO_CREATE_BODY_PROMPT_TEXT)


@router.message(StateFilter(AdminMacroStates.creating_body))
async def handle_admin_macro_create_body(
    message: Message,
    state: FSMContext,
) -> None:
    if await _validate_create_input(message, MACRO_CREATE_BODY_PROMPT_TEXT):
        return
    assert message.text is not None

    state_data = await state.get_data()
    title = state_data.get("draft_title")
    page = state_data.get("page", 1)
    if not isinstance(title, str):
        await state.clear()
        await message.answer(MACRO_DRAFT_LOST_TEXT)
        return

    await state.set_state(AdminMacroStates.creating_preview)
    await state.update_data(draft_body=message.text, page=page)
    await message.answer(
        format_admin_macro_create_preview(title=title, body=message.text),
        reply_markup=build_admin_macro_create_preview_markup(page=int(page)),
    )


@router.message(StateFilter(AdminMacroStates.creating_preview))
async def handle_admin_macro_create_preview_message(message: Message) -> None:
    await message.answer(MACRO_PREVIEW_COMMAND_BLOCK_TEXT)


async def _validate_create_input(message: Message, prompt_text: str) -> bool:
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
