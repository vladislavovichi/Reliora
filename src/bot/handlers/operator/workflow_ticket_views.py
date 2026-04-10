from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from application.use_cases.tickets.summaries import TicketDetailsSummary
from backend.grpc.contracts import HelpdeskBackendClientFactory
from bot.adapters.helpdesk import build_request_actor
from bot.callbacks import OperatorActionCallback
from bot.formatters.operator_ticket_views import format_ticket_details, format_ticket_more_actions
from bot.handlers.operator.active_context import activate_ticket_for_operator
from bot.handlers.operator.common import respond_to_operator
from bot.handlers.operator.parsers import parse_ticket_public_id
from bot.handlers.operator.ticket_surfaces import edit_ticket_main_surface, send_ticket_details
from bot.keyboards.inline.operator_actions import (
    build_ticket_actions_markup,
    build_ticket_more_actions_markup,
)
from bot.texts.common import (
    INVALID_TICKET_ID_TEXT,
    SERVICE_UNAVAILABLE_TEXT,
    TICKET_NOT_FOUND_TEXT,
)
from bot.texts.operator import (
    build_active_ticket_opened_text,
    build_more_actions_opened_text,
    build_view_opened_text,
)
from infrastructure.redis.contracts import (
    GlobalRateLimiter,
    OperatorActiveTicketStore,
    OperatorPresenceHelper,
    TicketLiveSessionStore,
)

router = Router(name="operator_workflow_ticket_views")


@router.callback_query(OperatorActionCallback.filter(F.action == "view"))
async def handle_view_action(
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

    if ticket_details is None:
        await respond_to_operator(callback, TICKET_NOT_FOUND_TEXT)
        return

    is_active_context = await activate_ticket_for_operator(
        active_ticket_store=operator_active_ticket_store,
        operator_telegram_user_id=callback.from_user.id,
        ticket_details=ticket_details,
        ticket_live_session_store=ticket_live_session_store,
    )
    await _answer_with_ticket_details(
        callback=callback,
        ticket_details=ticket_details,
        fallback_text=(
            build_active_ticket_opened_text(ticket_details.public_number)
            if is_active_context
            else build_view_opened_text(ticket_details.public_number)
        ),
        include_history=is_active_context,
        is_active_context=is_active_context,
    )


@router.callback_query(OperatorActionCallback.filter(F.action == "card"))
async def handle_card_action(
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
        format_ticket_details(ticket_details, is_active=is_active_context),
        reply_markup=build_ticket_actions_markup(
            ticket_public_id=ticket_details.public_id,
            status=ticket_details.status,
        ),
    )


@router.callback_query(OperatorActionCallback.filter(F.action == "more"))
async def handle_more_action(
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
        await callback.answer(build_more_actions_opened_text(ticket_details.public_number))
        return

    await callback.answer(build_more_actions_opened_text(ticket_details.public_number))
    await callback.message.edit_text(
        format_ticket_more_actions(ticket_details, is_active=is_active_context),
        reply_markup=build_ticket_more_actions_markup(
            ticket_public_id=ticket_details.public_id,
            status=ticket_details.status,
        ),
    )


@router.callback_query(OperatorActionCallback.filter(F.action == "back"))
async def handle_back_from_more_action(
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


async def _answer_with_ticket_details(
    *,
    callback: CallbackQuery,
    ticket_details: TicketDetailsSummary | None,
    fallback_text: str,
    include_history: bool = False,
    is_active_context: bool = False,
) -> None:
    if not isinstance(callback.message, Message) or ticket_details is None:
        await respond_to_operator(callback, fallback_text)
        return

    await callback.answer(fallback_text)
    await send_ticket_details(
        message=callback.message,
        ticket_details=ticket_details,
        include_history=include_history,
        is_active_context=is_active_context,
    )
