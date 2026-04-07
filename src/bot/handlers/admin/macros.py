from __future__ import annotations

from collections.abc import Sequence

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from application.services.helpdesk.service import HelpdeskServiceFactory
from application.use_cases.tickets.summaries import MacroManagementError, MacroSummary
from bot.callbacks import AdminMacroCallback
from bot.formatters.macros import (
    format_admin_macro_create_preview,
    format_admin_macro_details,
    format_admin_macro_list,
    paginate_macros,
)
from bot.handlers.admin.states import AdminMacroStates
from bot.handlers.operator.common import respond_to_operator
from bot.keyboards.inline.macros import (
    build_admin_macro_create_preview_markup,
    build_admin_macro_delete_markup,
    build_admin_macro_detail_markup,
    build_admin_macro_list_markup,
)
from bot.texts.buttons import ALL_NAVIGATION_BUTTONS, CANCEL_BUTTON_TEXT, MACROS_BUTTON_TEXT
from bot.texts.common import SERVICE_UNAVAILABLE_TEXT
from bot.texts.macros import (
    MACRO_BODY_EDIT_PROMPT_TEXT,
    MACRO_BODY_EDIT_STARTED_TEXT,
    MACRO_BODY_UPDATED_TEXT,
    MACRO_CREATE_BODY_PROMPT_TEXT,
    MACRO_CREATE_CANCELLED_TEXT,
    MACRO_CREATE_EDIT_TEXT,
    MACRO_CREATE_SAVED_TEXT,
    MACRO_CREATE_STARTED_TEXT,
    MACRO_CREATE_TITLE_PROMPT_TEXT,
    MACRO_DELETED_TEXT,
    MACRO_DRAFT_LOST_TEXT,
    MACRO_INPUT_COMMAND_BLOCK_TEXT,
    MACRO_INPUT_NAVIGATION_BLOCK_TEXT,
    MACRO_NOT_FOUND_TEXT,
    MACRO_PAGE_UPDATED_TEXT,
    MACRO_TITLE_EDIT_PROMPT_TEXT,
    MACRO_TITLE_EDIT_STARTED_TEXT,
    MACRO_TITLE_UPDATED_TEXT,
    build_macro_delete_prompt_text,
    build_macro_page_text,
)
from infrastructure.redis.contracts import GlobalRateLimiter, OperatorPresenceHelper

router = Router(name="admin_macros")


@router.message(F.text == MACROS_BUTTON_TEXT)
async def handle_admin_macros(
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
        macros = await helpdesk_service.list_macros(
            actor_telegram_user_id=message.from_user.id if message.from_user is not None else None
        )

    text, markup = _build_admin_macro_list_response(macros=macros, page=1)
    await message.answer(text, reply_markup=markup)


@router.callback_query(AdminMacroCallback.filter(F.action == "page"))
async def handle_admin_macro_page(
    callback: CallbackQuery,
    callback_data: AdminMacroCallback,
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
        macros = await helpdesk_service.list_macros(actor_telegram_user_id=callback.from_user.id)

    await _edit_admin_macro_list(
        callback=callback,
        macros=macros,
        page=callback_data.page,
        answer_text=MACRO_PAGE_UPDATED_TEXT,
    )


@router.callback_query(AdminMacroCallback.filter(F.action == "noop"))
async def handle_admin_macro_page_noop(
    callback: CallbackQuery,
    callback_data: AdminMacroCallback,
) -> None:
    await callback.answer(build_macro_page_text(callback_data.page))


@router.callback_query(AdminMacroCallback.filter(F.action == "view"))
async def handle_admin_macro_view(
    callback: CallbackQuery,
    callback_data: AdminMacroCallback,
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
        macro = await helpdesk_service.get_macro(
            macro_id=callback_data.macro_id,
            actor_telegram_user_id=callback.from_user.id,
        )

    if macro is None:
        await respond_to_operator(callback, MACRO_NOT_FOUND_TEXT)
        return

    await _edit_admin_macro_details(
        callback=callback,
        macro=macro,
        page=callback_data.page,
        answer_text=MACRO_PAGE_UPDATED_TEXT,
    )


@router.callback_query(AdminMacroCallback.filter(F.action == "back_list"))
async def handle_admin_macro_back_list(
    callback: CallbackQuery,
    callback_data: AdminMacroCallback,
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
        macros = await helpdesk_service.list_macros(actor_telegram_user_id=callback.from_user.id)

    await _edit_admin_macro_list(
        callback=callback,
        macros=macros,
        page=callback_data.page,
        answer_text=MACRO_PAGE_UPDATED_TEXT,
    )


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


@router.callback_query(AdminMacroCallback.filter(F.action == "edit_title"))
async def handle_admin_macro_edit_title(
    callback: CallbackQuery,
    callback_data: AdminMacroCallback,
    state: FSMContext,
) -> None:
    data = {
        "macro_id": callback_data.macro_id,
        "page": callback_data.page,
    }
    if isinstance(callback.message, Message):
        data["source_chat_id"] = callback.message.chat.id
        data["source_message_id"] = callback.message.message_id

    await state.set_state(AdminMacroStates.editing_title)
    await state.set_data(data)
    await respond_to_operator(callback, MACRO_TITLE_EDIT_STARTED_TEXT, MACRO_TITLE_EDIT_PROMPT_TEXT)


@router.callback_query(AdminMacroCallback.filter(F.action == "edit_body"))
async def handle_admin_macro_edit_body(
    callback: CallbackQuery,
    callback_data: AdminMacroCallback,
    state: FSMContext,
) -> None:
    data = {
        "macro_id": callback_data.macro_id,
        "page": callback_data.page,
    }
    if isinstance(callback.message, Message):
        data["source_chat_id"] = callback.message.chat.id
        data["source_message_id"] = callback.message.message_id

    await state.set_state(AdminMacroStates.editing_body)
    await state.set_data(data)
    await respond_to_operator(callback, MACRO_BODY_EDIT_STARTED_TEXT, MACRO_BODY_EDIT_PROMPT_TEXT)


@router.callback_query(AdminMacroCallback.filter(F.action == "delete"))
async def handle_admin_macro_delete_prompt(
    callback: CallbackQuery,
    callback_data: AdminMacroCallback,
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
        macro = await helpdesk_service.get_macro(
            macro_id=callback_data.macro_id,
            actor_telegram_user_id=callback.from_user.id,
        )

    if macro is None:
        await respond_to_operator(callback, MACRO_NOT_FOUND_TEXT)
        return
    if not isinstance(callback.message, Message):
        await callback.answer(MACRO_NOT_FOUND_TEXT)
        return

    await callback.answer(MACRO_PAGE_UPDATED_TEXT)
    await callback.message.edit_text(
        build_macro_delete_prompt_text(macro.title),
        reply_markup=build_admin_macro_delete_markup(
            macro_id=macro.id,
            page=callback_data.page,
        ),
    )


@router.callback_query(AdminMacroCallback.filter(F.action == "cancel_delete"))
async def handle_admin_macro_delete_cancel(
    callback: CallbackQuery,
    callback_data: AdminMacroCallback,
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
        macro = await helpdesk_service.get_macro(
            macro_id=callback_data.macro_id,
            actor_telegram_user_id=callback.from_user.id,
        )

    if macro is None:
        await respond_to_operator(callback, MACRO_NOT_FOUND_TEXT)
        return

    await _edit_admin_macro_details(
        callback=callback,
        macro=macro,
        page=callback_data.page,
        answer_text=MACRO_PAGE_UPDATED_TEXT,
    )


@router.callback_query(AdminMacroCallback.filter(F.action == "confirm_delete"))
async def handle_admin_macro_delete(
    callback: CallbackQuery,
    callback_data: AdminMacroCallback,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    if not await global_rate_limiter.allow():
        await respond_to_operator(callback, SERVICE_UNAVAILABLE_TEXT)
        return

    await operator_presence.touch(operator_id=callback.from_user.id)

    async with helpdesk_service_factory() as helpdesk_service:
        macro = await helpdesk_service.delete_macro(
            macro_id=callback_data.macro_id,
            actor_telegram_user_id=callback.from_user.id,
        )
        macros = await helpdesk_service.list_macros(actor_telegram_user_id=callback.from_user.id)

    if macro is None:
        await respond_to_operator(callback, MACRO_NOT_FOUND_TEXT)
        return

    await _edit_admin_macro_list(
        callback=callback,
        macros=macros,
        page=callback_data.page,
        answer_text=MACRO_DELETED_TEXT,
    )


@router.callback_query(AdminMacroCallback.filter(F.action == "preview_save"))
async def handle_admin_macro_preview_save(
    callback: CallbackQuery,
    callback_data: AdminMacroCallback,
    state: FSMContext,
    helpdesk_service_factory: HelpdeskServiceFactory,
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
        async with helpdesk_service_factory() as helpdesk_service:
            macro = await helpdesk_service.create_macro(
                title=title,
                body=body,
                actor_telegram_user_id=callback.from_user.id,
            )
    except MacroManagementError as exc:
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
    state: FSMContext,
) -> None:
    await state.clear()
    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer(MACRO_CREATE_CANCELLED_TEXT)


@router.message(StateFilter(AdminMacroStates.creating_title))
async def handle_admin_macro_create_title(
    message: Message,
    state: FSMContext,
) -> None:
    if message.text is None:
        await message.answer(MACRO_CREATE_TITLE_PROMPT_TEXT)
        return
    if message.text in ALL_NAVIGATION_BUTTONS and message.text != CANCEL_BUTTON_TEXT:
        await message.answer(MACRO_INPUT_NAVIGATION_BLOCK_TEXT)
        return
    if message.text.startswith("/"):
        await message.answer(MACRO_INPUT_COMMAND_BLOCK_TEXT)
        return

    await state.set_state(AdminMacroStates.creating_body)
    await state.update_data(draft_title=message.text)
    await message.answer(MACRO_CREATE_BODY_PROMPT_TEXT)


@router.message(StateFilter(AdminMacroStates.creating_body))
async def handle_admin_macro_create_body(
    message: Message,
    state: FSMContext,
) -> None:
    if message.text is None:
        await message.answer(MACRO_CREATE_BODY_PROMPT_TEXT)
        return
    if message.text in ALL_NAVIGATION_BUTTONS and message.text != CANCEL_BUTTON_TEXT:
        await message.answer(MACRO_INPUT_NAVIGATION_BLOCK_TEXT)
        return
    if message.text.startswith("/"):
        await message.answer(MACRO_INPUT_COMMAND_BLOCK_TEXT)
        return

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
    await message.answer(MACRO_INPUT_COMMAND_BLOCK_TEXT)


@router.message(StateFilter(AdminMacroStates.editing_title))
async def handle_admin_macro_edit_title_message(
    message: Message,
    state: FSMContext,
    bot: Bot,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    if message.text is None:
        await message.answer(MACRO_TITLE_EDIT_PROMPT_TEXT)
        return
    if message.text in ALL_NAVIGATION_BUTTONS and message.text != CANCEL_BUTTON_TEXT:
        await message.answer(MACRO_INPUT_NAVIGATION_BLOCK_TEXT)
        return
    if message.text.startswith("/"):
        await message.answer(MACRO_INPUT_COMMAND_BLOCK_TEXT)
        return
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
        async with helpdesk_service_factory() as helpdesk_service:
            macro = await helpdesk_service.update_macro_title(
                macro_id=macro_id,
                title=message.text,
                actor_telegram_user_id=message.from_user.id,
            )
    except MacroManagementError as exc:
        await message.answer(str(exc))
        return

    await state.clear()
    if macro is None:
        await message.answer(MACRO_NOT_FOUND_TEXT)
        return

    await message.answer(MACRO_TITLE_UPDATED_TEXT)
    await _update_admin_source_message(
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
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    if message.text is None:
        await message.answer(MACRO_BODY_EDIT_PROMPT_TEXT)
        return
    if message.text in ALL_NAVIGATION_BUTTONS and message.text != CANCEL_BUTTON_TEXT:
        await message.answer(MACRO_INPUT_NAVIGATION_BLOCK_TEXT)
        return
    if message.text.startswith("/"):
        await message.answer(MACRO_INPUT_COMMAND_BLOCK_TEXT)
        return
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
        async with helpdesk_service_factory() as helpdesk_service:
            macro = await helpdesk_service.update_macro_body(
                macro_id=macro_id,
                body=message.text,
                actor_telegram_user_id=message.from_user.id,
            )
    except MacroManagementError as exc:
        await message.answer(str(exc))
        return

    await state.clear()
    if macro is None:
        await message.answer(MACRO_NOT_FOUND_TEXT)
        return

    await message.answer(MACRO_BODY_UPDATED_TEXT)
    await _update_admin_source_message(
        bot=bot,
        state_data=state_data,
        macro=macro,
        page=page,
        fallback_message=message,
    )


def _build_admin_macro_list_response(
    *,
    macros: Sequence[MacroSummary],
    page: int,
) -> tuple[str, InlineKeyboardMarkup]:
    page_macros, current_page, total_pages = paginate_macros(macros, page=page)
    return (
        format_admin_macro_list(
            page_macros,
            current_page=current_page,
            total_pages=total_pages,
        ),
        build_admin_macro_list_markup(
            macros=page_macros,
            current_page=current_page,
            total_pages=total_pages,
        ),
    )


async def _edit_admin_macro_list(
    *,
    callback: CallbackQuery,
    macros: Sequence[MacroSummary],
    page: int,
    answer_text: str,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer(answer_text)
        return
    text, markup = _build_admin_macro_list_response(macros=macros, page=page)
    await callback.answer(answer_text)
    await callback.message.edit_text(text, reply_markup=markup)


async def _edit_admin_macro_details(
    *,
    callback: CallbackQuery,
    macro: MacroSummary,
    page: int,
    answer_text: str,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer(answer_text)
        return
    await callback.answer(answer_text)
    await callback.message.edit_text(
        format_admin_macro_details(macro),
        reply_markup=build_admin_macro_detail_markup(
            macro_id=macro.id,
            page=page,
        ),
    )


async def _update_admin_source_message(
    *,
    bot: Bot,
    state_data: dict[str, object],
    macro: MacroSummary,
    page: int,
    fallback_message: Message,
) -> None:
    chat_id = state_data.get("source_chat_id")
    message_id = state_data.get("source_message_id")
    if isinstance(chat_id, int) and isinstance(message_id, int):
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=format_admin_macro_details(macro),
            reply_markup=build_admin_macro_detail_markup(
                macro_id=macro.id,
                page=page,
            ),
        )
        return

    await fallback_message.answer(
        format_admin_macro_details(macro),
        reply_markup=build_admin_macro_detail_markup(
            macro_id=macro.id,
            page=page,
        ),
    )
