from __future__ import annotations

from collections.abc import Sequence

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from application.use_cases.tickets.summaries import MacroSummary, TicketDetailsSummary
from backend.grpc.contracts import HelpdeskBackendClientFactory
from bot.adapters.helpdesk import build_request_actor
from bot.callbacks import OperatorActionCallback, OperatorMacroCallback
from bot.formatters.macros import (
    format_operator_macro_picker,
    format_operator_macro_preview,
    paginate_macros,
)
from bot.handlers.operator.active_context import activate_ticket_for_operator
from bot.handlers.operator.common import respond_to_operator
from bot.handlers.operator.parsers import parse_ticket_public_id
from bot.handlers.operator.ticket_surfaces import edit_ticket_main_surface
from bot.keyboards.inline.macros import (
    build_operator_macro_picker_markup,
    build_operator_macro_preview_markup,
)
from bot.texts.common import (
    INVALID_TICKET_ID_TEXT,
    SERVICE_UNAVAILABLE_TEXT,
    TICKET_NOT_FOUND_TEXT,
)
from bot.texts.macros import (
    MACRO_NOT_FOUND_TEXT,
    MACRO_PAGE_UPDATED_TEXT,
    MACRO_PICKER_OPENED_TEXT,
    build_macro_page_text,
)
from bot.texts.operator import (
    MACROS_EMPTY_TEXT,
    build_active_ticket_opened_text,
    build_view_opened_text,
)
from infrastructure.redis.contracts import (
    GlobalRateLimiter,
    OperatorActiveTicketStore,
    OperatorPresenceHelper,
    TicketLiveSessionStore,
)

router = Router(name="operator_workflow_macro_browser")


@router.callback_query(OperatorActionCallback.filter(F.action == "macros"))
async def handle_open_macros(
    callback: CallbackQuery,
    callback_data: OperatorActionCallback,
    helpdesk_backend_client_factory: HelpdeskBackendClientFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
    operator_active_ticket_store: OperatorActiveTicketStore,
    ticket_live_session_store: TicketLiveSessionStore,
) -> None:
    ticket_public_id = parse_ticket_public_id(callback_data.ticket_public_id)
    if ticket_public_id is None:
        await respond_to_operator(callback, INVALID_TICKET_ID_TEXT)
        return
    if not await global_rate_limiter.allow():
        await respond_to_operator(callback, SERVICE_UNAVAILABLE_TEXT)
        return

    await operator_presence.touch(operator_id=callback.from_user.id)
    async with helpdesk_backend_client_factory() as helpdesk_backend:
        ticket_details = await helpdesk_backend.get_ticket_details(
            ticket_public_id=ticket_public_id,
            actor=build_request_actor(callback.from_user),
        )
        macros = await helpdesk_backend.list_macros(actor=build_request_actor(callback.from_user))

    if ticket_details is None:
        await respond_to_operator(callback, TICKET_NOT_FOUND_TEXT)
        return

    is_active_context = await activate_ticket_for_operator(
        active_ticket_store=operator_active_ticket_store,
        operator_telegram_user_id=callback.from_user.id,
        ticket_details=ticket_details,
        ticket_live_session_store=ticket_live_session_store,
    )
    if not macros:
        await edit_ticket_main_surface(
            callback=callback,
            ticket_details=ticket_details,
            answer_text=MACROS_EMPTY_TEXT,
            is_active_context=is_active_context,
        )
        return

    await _render_picker(
        callback=callback,
        ticket_details=ticket_details,
        macros=macros,
        page=1,
        answer_text=MACRO_PICKER_OPENED_TEXT,
    )


@router.callback_query(OperatorMacroCallback.filter(F.action == "page"))
async def handle_macro_page(
    callback: CallbackQuery,
    callback_data: OperatorMacroCallback,
    helpdesk_backend_client_factory: HelpdeskBackendClientFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
    operator_active_ticket_store: OperatorActiveTicketStore,
    ticket_live_session_store: TicketLiveSessionStore,
) -> None:
    ticket_public_id = parse_ticket_public_id(callback_data.ticket_public_id)
    if ticket_public_id is None:
        await respond_to_operator(callback, INVALID_TICKET_ID_TEXT)
        return
    if not await global_rate_limiter.allow():
        await respond_to_operator(callback, SERVICE_UNAVAILABLE_TEXT)
        return

    await operator_presence.touch(operator_id=callback.from_user.id)
    async with helpdesk_backend_client_factory() as helpdesk_backend:
        ticket_details = await helpdesk_backend.get_ticket_details(
            ticket_public_id=ticket_public_id,
            actor=build_request_actor(callback.from_user),
        )
        macros = await helpdesk_backend.list_macros(actor=build_request_actor(callback.from_user))

    if ticket_details is None:
        await respond_to_operator(callback, TICKET_NOT_FOUND_TEXT)
        return

    is_active_context = await activate_ticket_for_operator(
        active_ticket_store=operator_active_ticket_store,
        operator_telegram_user_id=callback.from_user.id,
        ticket_details=ticket_details,
        ticket_live_session_store=ticket_live_session_store,
    )
    if not macros:
        await edit_ticket_main_surface(
            callback=callback,
            ticket_details=ticket_details,
            answer_text=MACROS_EMPTY_TEXT,
            is_active_context=is_active_context,
        )
        return

    await _render_picker(
        callback=callback,
        ticket_details=ticket_details,
        macros=macros,
        page=callback_data.page,
        answer_text=MACRO_PAGE_UPDATED_TEXT,
    )


@router.callback_query(OperatorMacroCallback.filter(F.action == "noop"))
async def handle_macro_page_noop(
    callback: CallbackQuery,
    callback_data: OperatorMacroCallback,
) -> None:
    await callback.answer(build_macro_page_text(callback_data.page))


@router.callback_query(OperatorMacroCallback.filter(F.action == "preview"))
async def handle_macro_preview(
    callback: CallbackQuery,
    callback_data: OperatorMacroCallback,
    helpdesk_backend_client_factory: HelpdeskBackendClientFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
    operator_active_ticket_store: OperatorActiveTicketStore,
    ticket_live_session_store: TicketLiveSessionStore,
) -> None:
    ticket_public_id = parse_ticket_public_id(callback_data.ticket_public_id)
    if ticket_public_id is None:
        await respond_to_operator(callback, INVALID_TICKET_ID_TEXT)
        return
    if not await global_rate_limiter.allow():
        await respond_to_operator(callback, SERVICE_UNAVAILABLE_TEXT)
        return

    await operator_presence.touch(operator_id=callback.from_user.id)
    async with helpdesk_backend_client_factory() as helpdesk_backend:
        ticket_details = await helpdesk_backend.get_ticket_details(
            ticket_public_id=ticket_public_id,
            actor=build_request_actor(callback.from_user),
        )
        macros = await helpdesk_backend.list_macros(actor=build_request_actor(callback.from_user))

    if ticket_details is None:
        await respond_to_operator(callback, TICKET_NOT_FOUND_TEXT)
        return

    is_active_context = await activate_ticket_for_operator(
        active_ticket_store=operator_active_ticket_store,
        operator_telegram_user_id=callback.from_user.id,
        ticket_details=ticket_details,
        ticket_live_session_store=ticket_live_session_store,
    )

    macro = next((item for item in macros if item.id == callback_data.macro_id), None)
    if macro is None:
        if macros:
            await _render_picker(
                callback=callback,
                ticket_details=ticket_details,
                macros=macros,
                page=callback_data.page,
                answer_text=MACRO_NOT_FOUND_TEXT,
            )
            return

        await edit_ticket_main_surface(
            callback=callback,
            ticket_details=ticket_details,
            answer_text=MACRO_NOT_FOUND_TEXT,
            is_active_context=is_active_context,
        )
        return

    if not isinstance(callback.message, Message):
        await callback.answer(MACRO_PICKER_OPENED_TEXT)
        return

    await callback.answer(MACRO_PICKER_OPENED_TEXT)
    await callback.message.edit_text(
        format_operator_macro_preview(
            ticket_public_number=ticket_details.public_number,
            macro=macro,
        ),
        reply_markup=build_operator_macro_preview_markup(
            ticket_public_id=ticket_details.public_id,
            macro_id=macro.id,
            page=callback_data.page,
        ),
    )


@router.callback_query(OperatorMacroCallback.filter(F.action == "back"))
async def handle_macro_preview_back(
    callback: CallbackQuery,
    callback_data: OperatorMacroCallback,
    helpdesk_backend_client_factory: HelpdeskBackendClientFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
    operator_active_ticket_store: OperatorActiveTicketStore,
    ticket_live_session_store: TicketLiveSessionStore,
) -> None:
    ticket_public_id = parse_ticket_public_id(callback_data.ticket_public_id)
    if ticket_public_id is None:
        await respond_to_operator(callback, INVALID_TICKET_ID_TEXT)
        return
    if not await global_rate_limiter.allow():
        await respond_to_operator(callback, SERVICE_UNAVAILABLE_TEXT)
        return

    await operator_presence.touch(operator_id=callback.from_user.id)
    async with helpdesk_backend_client_factory() as helpdesk_backend:
        ticket_details = await helpdesk_backend.get_ticket_details(
            ticket_public_id=ticket_public_id,
            actor=build_request_actor(callback.from_user),
        )
        macros = await helpdesk_backend.list_macros(actor=build_request_actor(callback.from_user))

    if ticket_details is None:
        await respond_to_operator(callback, TICKET_NOT_FOUND_TEXT)
        return

    is_active_context = await activate_ticket_for_operator(
        active_ticket_store=operator_active_ticket_store,
        operator_telegram_user_id=callback.from_user.id,
        ticket_details=ticket_details,
        ticket_live_session_store=ticket_live_session_store,
    )
    if not macros:
        await edit_ticket_main_surface(
            callback=callback,
            ticket_details=ticket_details,
            answer_text=MACROS_EMPTY_TEXT,
            is_active_context=is_active_context,
        )
        return

    await _render_picker(
        callback=callback,
        ticket_details=ticket_details,
        macros=macros,
        page=callback_data.page,
        answer_text=MACRO_PAGE_UPDATED_TEXT,
    )


@router.callback_query(OperatorMacroCallback.filter(F.action == "ticket"))
async def handle_macro_ticket_back(
    callback: CallbackQuery,
    callback_data: OperatorMacroCallback,
    helpdesk_backend_client_factory: HelpdeskBackendClientFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
    operator_active_ticket_store: OperatorActiveTicketStore,
    ticket_live_session_store: TicketLiveSessionStore,
) -> None:
    ticket_public_id = parse_ticket_public_id(callback_data.ticket_public_id)
    if ticket_public_id is None:
        await respond_to_operator(callback, INVALID_TICKET_ID_TEXT)
        return
    if not await global_rate_limiter.allow():
        await respond_to_operator(callback, SERVICE_UNAVAILABLE_TEXT)
        return

    await operator_presence.touch(operator_id=callback.from_user.id)
    async with helpdesk_backend_client_factory() as helpdesk_backend:
        ticket_details = await helpdesk_backend.get_ticket_details(
            ticket_public_id=ticket_public_id,
            actor=build_request_actor(callback.from_user),
        )

    if ticket_details is None:
        await respond_to_operator(callback, TICKET_NOT_FOUND_TEXT)
        return

    is_active_context = await activate_ticket_for_operator(
        active_ticket_store=operator_active_ticket_store,
        operator_telegram_user_id=callback.from_user.id,
        ticket_details=ticket_details,
        ticket_live_session_store=ticket_live_session_store,
    )
    await edit_ticket_main_surface(
        callback=callback,
        ticket_details=ticket_details,
        answer_text=(
            build_active_ticket_opened_text(ticket_details.public_number)
            if is_active_context
            else build_view_opened_text(ticket_details.public_number)
        ),
        is_active_context=is_active_context,
    )


async def _render_picker(
    *,
    callback: CallbackQuery,
    ticket_details: TicketDetailsSummary,
    macros: Sequence[MacroSummary],
    page: int,
    answer_text: str,
) -> None:
    page_macros, current_page, total_pages = paginate_macros(macros, page=page)

    if not isinstance(callback.message, Message):
        await callback.answer(answer_text)
        return

    await callback.answer(answer_text)
    await callback.message.edit_text(
        format_operator_macro_picker(
            ticket_public_number=ticket_details.public_number,
            macros=page_macros,
            current_page=current_page,
            total_pages=total_pages,
        ),
        reply_markup=build_operator_macro_picker_markup(
            ticket_public_id=ticket_details.public_id,
            macros=page_macros,
            current_page=current_page,
            total_pages=total_pages,
        ),
    )
