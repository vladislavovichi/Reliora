from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from application.contracts.runtime import GlobalRateLimiter, OperatorPresenceHelper
from backend.grpc.contracts import HelpdeskBackendClientFactory
from bot.adapters.helpdesk import build_request_actor
from bot.callbacks import AdminMacroCallback
from bot.handlers.admin.macro_surfaces import (
    build_admin_macro_list_response,
    edit_admin_macro_details,
    edit_admin_macro_list,
)
from bot.handlers.operator.common import respond_to_operator
from bot.keyboards.inline.macros import build_admin_macro_delete_markup
from bot.texts.buttons import MACROS_BUTTON_TEXT
from bot.texts.common import SERVICE_UNAVAILABLE_TEXT
from bot.texts.macros import (
    MACRO_DELETED_TEXT,
    MACRO_NOT_FOUND_TEXT,
    MACRO_PAGE_UPDATED_TEXT,
    build_macro_delete_prompt_text,
    build_macro_page_text,
)

router = Router(name="admin_macro_browser")


@router.message(F.text == MACROS_BUTTON_TEXT)
async def handle_admin_macros(
    message: Message,
    state: FSMContext,
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
        macros = await helpdesk_backend.list_macros(actor=build_request_actor(message.from_user))

    text, markup = build_admin_macro_list_response(macros=macros, page=1)
    await message.answer(text, reply_markup=markup)


@router.callback_query(AdminMacroCallback.filter(F.action == "page"))
async def handle_admin_macro_page(
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
        macro = await helpdesk_backend.get_macro(
            macro_id=callback_data.macro_id,
            actor=build_request_actor(callback.from_user),
        )

    if macro is None:
        async with helpdesk_backend_client_factory() as helpdesk_backend:
            macros = await helpdesk_backend.list_macros(
                actor=build_request_actor(callback.from_user)
            )

        await edit_admin_macro_list(
            callback=callback,
            macros=macros,
            page=callback_data.page,
            answer_text=MACRO_NOT_FOUND_TEXT,
        )
        return

    await edit_admin_macro_details(
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
        answer_text=MACRO_PAGE_UPDATED_TEXT,
    )


@router.callback_query(AdminMacroCallback.filter(F.action == "delete"))
async def handle_admin_macro_delete_prompt(
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
        macro = await helpdesk_backend.get_macro(
            macro_id=callback_data.macro_id,
            actor=build_request_actor(callback.from_user),
        )

    if macro is None:
        async with helpdesk_backend_client_factory() as helpdesk_backend:
            macros = await helpdesk_backend.list_macros(
                actor=build_request_actor(callback.from_user)
            )

        await edit_admin_macro_list(
            callback=callback,
            macros=macros,
            page=callback_data.page,
            answer_text=MACRO_NOT_FOUND_TEXT,
        )
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
        macro = await helpdesk_backend.get_macro(
            macro_id=callback_data.macro_id,
            actor=build_request_actor(callback.from_user),
        )

    if macro is None:
        async with helpdesk_backend_client_factory() as helpdesk_backend:
            macros = await helpdesk_backend.list_macros(
                actor=build_request_actor(callback.from_user)
            )

        await edit_admin_macro_list(
            callback=callback,
            macros=macros,
            page=callback_data.page,
            answer_text=MACRO_NOT_FOUND_TEXT,
        )
        return

    await edit_admin_macro_details(
        callback=callback,
        macro=macro,
        page=callback_data.page,
        answer_text=MACRO_PAGE_UPDATED_TEXT,
    )


@router.callback_query(AdminMacroCallback.filter(F.action == "confirm_delete"))
async def handle_admin_macro_delete(
    callback: CallbackQuery,
    callback_data: AdminMacroCallback,
    helpdesk_backend_client_factory: HelpdeskBackendClientFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    if not await global_rate_limiter.allow():
        await respond_to_operator(callback, SERVICE_UNAVAILABLE_TEXT)
        return

    await operator_presence.touch(operator_id=callback.from_user.id)

    async with helpdesk_backend_client_factory() as helpdesk_backend:
        macro = await helpdesk_backend.delete_macro(
            macro_id=callback_data.macro_id,
            actor=build_request_actor(callback.from_user),
        )
        macros = await helpdesk_backend.list_macros(actor=build_request_actor(callback.from_user))

    if macro is None:
        await edit_admin_macro_list(
            callback=callback,
            macros=macros,
            page=callback_data.page,
            answer_text=MACRO_NOT_FOUND_TEXT,
        )
        return

    await edit_admin_macro_list(
        callback=callback,
        macros=macros,
        page=callback_data.page,
        answer_text=MACRO_DELETED_TEXT,
    )
