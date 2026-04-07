from __future__ import annotations

import logging
from collections.abc import Sequence

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, Message

from application.services.helpdesk.service import HelpdeskServiceFactory
from application.use_cases.tickets.summaries import MacroSummary, TicketDetailsSummary
from bot.callbacks import OperatorActionCallback, OperatorMacroCallback
from bot.delivery import deliver_text_to_chat
from bot.formatters.macros import (
    format_operator_macro_picker,
    format_operator_macro_preview,
    paginate_macros,
)
from bot.formatters.operator import format_active_ticket_context, format_ticket_details
from bot.handlers.operator.active_context import activate_ticket_for_operator
from bot.handlers.operator.common import respond_to_operator
from bot.handlers.operator.parsers import parse_ticket_public_id
from bot.keyboards.inline.client_actions import build_client_ticket_markup
from bot.keyboards.inline.macros import (
    build_operator_macro_picker_markup,
    build_operator_macro_preview_markup,
)
from bot.keyboards.inline.operator_actions import build_ticket_actions_markup
from bot.texts.common import (
    INVALID_TICKET_ID_TEXT,
    SERVICE_UNAVAILABLE_TEXT,
    TICKET_LOCKED_TEXT,
    TICKET_NOT_FOUND_TEXT,
)
from bot.texts.macros import (
    MACRO_NOT_FOUND_TEXT,
    MACRO_PAGE_UPDATED_TEXT,
    MACRO_PICKER_OPENED_TEXT,
    build_macro_page_text,
)
from bot.texts.operator import (
    APPLY_MACRO_FAILED_TEXT,
    MACROS_EMPTY_TEXT,
    build_macro_delivery_failed_text,
    build_macro_saved_text,
    build_macro_sent_text,
    build_view_opened_text,
)
from domain.tickets import InvalidTicketTransitionError
from infrastructure.redis.contracts import (
    GlobalRateLimiter,
    OperatorActiveTicketStore,
    OperatorPresenceHelper,
    TicketLiveSessionStore,
    TicketLockManager,
)

router = Router(name="operator_workflow_macro_actions")
logger = logging.getLogger(__name__)


@router.callback_query(OperatorActionCallback.filter(F.action == "macros"))
async def handle_open_macros(
    callback: CallbackQuery,
    callback_data: OperatorActionCallback,
    helpdesk_service_factory: HelpdeskServiceFactory,
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

    async with helpdesk_service_factory() as helpdesk_service:
        ticket_details = await helpdesk_service.get_ticket_details(
            ticket_public_id=ticket_public_id,
            actor_telegram_user_id=callback.from_user.id,
        )
        macros = await helpdesk_service.list_macros(actor_telegram_user_id=callback.from_user.id)

    if ticket_details is None:
        await respond_to_operator(callback, TICKET_NOT_FOUND_TEXT)
        return
    if not macros:
        await respond_to_operator(callback, MACROS_EMPTY_TEXT)
        return

    await activate_ticket_for_operator(
        active_ticket_store=operator_active_ticket_store,
        operator_telegram_user_id=callback.from_user.id,
        ticket_details=ticket_details,
        ticket_live_session_store=ticket_live_session_store,
    )

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
    helpdesk_service_factory: HelpdeskServiceFactory,
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

    async with helpdesk_service_factory() as helpdesk_service:
        ticket_details = await helpdesk_service.get_ticket_details(
            ticket_public_id=ticket_public_id,
            actor_telegram_user_id=callback.from_user.id,
        )
        macros = await helpdesk_service.list_macros(actor_telegram_user_id=callback.from_user.id)

    if ticket_details is None:
        await respond_to_operator(callback, TICKET_NOT_FOUND_TEXT)
        return
    if not macros:
        await respond_to_operator(callback, MACROS_EMPTY_TEXT)
        return

    await activate_ticket_for_operator(
        active_ticket_store=operator_active_ticket_store,
        operator_telegram_user_id=callback.from_user.id,
        ticket_details=ticket_details,
        ticket_live_session_store=ticket_live_session_store,
    )

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
    helpdesk_service_factory: HelpdeskServiceFactory,
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

    async with helpdesk_service_factory() as helpdesk_service:
        ticket_details = await helpdesk_service.get_ticket_details(
            ticket_public_id=ticket_public_id,
            actor_telegram_user_id=callback.from_user.id,
        )
        macros = await helpdesk_service.list_macros(actor_telegram_user_id=callback.from_user.id)

    if ticket_details is None:
        await respond_to_operator(callback, TICKET_NOT_FOUND_TEXT)
        return

    await activate_ticket_for_operator(
        active_ticket_store=operator_active_ticket_store,
        operator_telegram_user_id=callback.from_user.id,
        ticket_details=ticket_details,
        ticket_live_session_store=ticket_live_session_store,
    )

    macro = next((item for item in macros if item.id == callback_data.macro_id), None)
    if macro is None:
        await respond_to_operator(callback, MACRO_NOT_FOUND_TEXT)
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
    helpdesk_service_factory: HelpdeskServiceFactory,
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

    async with helpdesk_service_factory() as helpdesk_service:
        ticket_details = await helpdesk_service.get_ticket_details(
            ticket_public_id=ticket_public_id,
            actor_telegram_user_id=callback.from_user.id,
        )
        macros = await helpdesk_service.list_macros(actor_telegram_user_id=callback.from_user.id)

    if ticket_details is None:
        await respond_to_operator(callback, TICKET_NOT_FOUND_TEXT)
        return
    if not macros:
        await respond_to_operator(callback, MACROS_EMPTY_TEXT)
        return

    await activate_ticket_for_operator(
        active_ticket_store=operator_active_ticket_store,
        operator_telegram_user_id=callback.from_user.id,
        ticket_details=ticket_details,
        ticket_live_session_store=ticket_live_session_store,
    )

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
    helpdesk_service_factory: HelpdeskServiceFactory,
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

    async with helpdesk_service_factory() as helpdesk_service:
        ticket_details = await helpdesk_service.get_ticket_details(
            ticket_public_id=ticket_public_id,
            actor_telegram_user_id=callback.from_user.id,
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
    if not isinstance(callback.message, Message):
        await callback.answer(build_view_opened_text(ticket_details.public_number))
        return

    await callback.answer(build_view_opened_text(ticket_details.public_number))
    await callback.message.edit_text(
        (
            format_active_ticket_context(ticket_details)
            if is_active_context
            else format_ticket_details(ticket_details)
        ),
        reply_markup=build_ticket_actions_markup(
            ticket_public_id=ticket_details.public_id,
            status=ticket_details.status,
        ),
    )


@router.callback_query(OperatorMacroCallback.filter(F.action == "apply"))
async def handle_apply_macro(
    callback: CallbackQuery,
    callback_data: OperatorMacroCallback,
    bot: Bot,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
    operator_active_ticket_store: OperatorActiveTicketStore,
    ticket_live_session_store: TicketLiveSessionStore,
    ticket_lock_manager: TicketLockManager,
) -> None:
    ticket_public_id = parse_ticket_public_id(callback_data.ticket_public_id)
    if ticket_public_id is None:
        await respond_to_operator(callback, INVALID_TICKET_ID_TEXT)
        return
    if not await global_rate_limiter.allow():
        await respond_to_operator(callback, SERVICE_UNAVAILABLE_TEXT)
        return

    await operator_presence.touch(operator_id=callback.from_user.id)

    lock = ticket_lock_manager.for_ticket(callback_data.ticket_public_id)
    if not await lock.acquire():
        await respond_to_operator(callback, TICKET_LOCKED_TEXT)
        return

    macro_result = None
    ticket_details = None
    error_message: str | None = None
    try:
        async with helpdesk_service_factory() as helpdesk_service:
            try:
                macro_result = await helpdesk_service.apply_macro_to_ticket(
                    ticket_public_id=ticket_public_id,
                    macro_id=callback_data.macro_id,
                    telegram_user_id=callback.from_user.id,
                    display_name=callback.from_user.full_name,
                    username=callback.from_user.username,
                    actor_telegram_user_id=callback.from_user.id,
                )
            except InvalidTicketTransitionError as exc:
                error_message = str(exc)

            if macro_result is not None:
                ticket_details = await helpdesk_service.get_ticket_details(
                    ticket_public_id=ticket_public_id,
                    actor_telegram_user_id=callback.from_user.id,
                )
    finally:
        await lock.release()

    if error_message is not None:
        await respond_to_operator(callback, error_message)
        return
    if macro_result is None:
        await respond_to_operator(callback, APPLY_MACRO_FAILED_TEXT)
        return

    is_active_context = False
    if ticket_details is not None:
        is_active_context = await activate_ticket_for_operator(
            active_ticket_store=operator_active_ticket_store,
            operator_telegram_user_id=callback.from_user.id,
            ticket_details=ticket_details,
            ticket_live_session_store=ticket_live_session_store,
        )

    delivery_error = await deliver_text_to_chat(
        bot,
        chat_id=macro_result.client_chat_id,
        text=macro_result.macro.body,
        reply_markup=build_client_ticket_markup(ticket_public_id=ticket_public_id),
        logger=logger,
        operation="apply_macro",
    )

    answer_text = build_macro_sent_text(macro_result.macro.title)
    if delivery_error is not None:
        answer_text = build_macro_saved_text(macro_result.macro.title)

    if not isinstance(callback.message, Message) or ticket_details is None:
        message_text = None
        if delivery_error is not None:
            message_text = build_macro_delivery_failed_text(
                macro_result.macro.title,
                delivery_error,
            )
        await respond_to_operator(callback, answer_text, message_text)
        return

    await callback.answer(answer_text)
    if delivery_error is not None:
        await callback.message.answer(
            build_macro_delivery_failed_text(macro_result.macro.title, delivery_error)
        )

    await callback.message.edit_text(
        (
            format_active_ticket_context(ticket_details)
            if is_active_context
            else format_ticket_details(ticket_details)
        ),
        reply_markup=build_ticket_actions_markup(
            ticket_public_id=ticket_details.public_id,
            status=ticket_details.status,
        ),
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
