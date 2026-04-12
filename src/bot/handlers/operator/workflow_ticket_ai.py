from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from backend.grpc.contracts import HelpdeskBackendClientFactory
from bot.adapters.helpdesk import build_request_actor
from bot.callbacks import OperatorActionCallback
from bot.formatters.operator_ai import format_ticket_assist_snapshot
from bot.handlers.operator.active_context import activate_ticket_for_operator
from bot.handlers.operator.common import respond_to_operator
from bot.handlers.operator.parsers import parse_ticket_public_id
from bot.keyboards.inline.operator_actions import build_ticket_assist_markup
from bot.texts.common import (
    INVALID_TICKET_ID_TEXT,
    SERVICE_UNAVAILABLE_TEXT,
    TICKET_NOT_FOUND_TEXT,
)
from bot.texts.operator import build_assist_opened_text
from infrastructure.redis.contracts import (
    GlobalRateLimiter,
    OperatorActiveTicketStore,
    OperatorPresenceHelper,
    TicketLiveSessionStore,
)

router = Router(name="operator_workflow_ticket_ai")


@router.callback_query(OperatorActionCallback.filter(F.action == "assist"))
async def handle_ticket_assist_action(
    callback: CallbackQuery,
    callback_data: OperatorActionCallback,
    helpdesk_backend_client_factory: HelpdeskBackendClientFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
    operator_active_ticket_store: OperatorActiveTicketStore,
    ticket_live_session_store: TicketLiveSessionStore,
) -> None:
    await _render_ticket_assist_surface(
        callback=callback,
        ticket_public_id_value=callback_data.ticket_public_id,
        helpdesk_backend_client_factory=helpdesk_backend_client_factory,
        global_rate_limiter=global_rate_limiter,
        operator_presence=operator_presence,
        operator_active_ticket_store=operator_active_ticket_store,
        ticket_live_session_store=ticket_live_session_store,
        refresh_summary=False,
    )


@router.callback_query(OperatorActionCallback.filter(F.action == "assist_refresh"))
async def handle_ticket_assist_refresh_action(
    callback: CallbackQuery,
    callback_data: OperatorActionCallback,
    helpdesk_backend_client_factory: HelpdeskBackendClientFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
    operator_active_ticket_store: OperatorActiveTicketStore,
    ticket_live_session_store: TicketLiveSessionStore,
) -> None:
    await _render_ticket_assist_surface(
        callback=callback,
        ticket_public_id_value=callback_data.ticket_public_id,
        helpdesk_backend_client_factory=helpdesk_backend_client_factory,
        global_rate_limiter=global_rate_limiter,
        operator_presence=operator_presence,
        operator_active_ticket_store=operator_active_ticket_store,
        ticket_live_session_store=ticket_live_session_store,
        refresh_summary=True,
    )


async def _render_ticket_assist_surface(
    *,
    callback: CallbackQuery,
    ticket_public_id_value: str,
    helpdesk_backend_client_factory: HelpdeskBackendClientFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
    operator_active_ticket_store: OperatorActiveTicketStore,
    ticket_live_session_store: TicketLiveSessionStore,
    refresh_summary: bool,
) -> None:
    ticket_public_id = parse_ticket_public_id(ticket_public_id_value)
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
        snapshot = await helpdesk_backend.get_ticket_ai_assist_snapshot(
            ticket_public_id=ticket_public_id,
            refresh_summary=refresh_summary,
            actor=build_request_actor(callback.from_user),
        )

    if ticket_details is None or snapshot is None:
        await respond_to_operator(callback, TICKET_NOT_FOUND_TEXT)
        return

    await activate_ticket_for_operator(
        active_ticket_store=operator_active_ticket_store,
        operator_telegram_user_id=callback.from_user.id,
        ticket_details=ticket_details,
        ticket_live_session_store=ticket_live_session_store,
    )
    if not isinstance(callback.message, Message):
        await callback.answer(build_assist_opened_text(ticket_details.public_number))
        return

    await callback.answer(build_assist_opened_text(ticket_details.public_number))
    await callback.message.edit_text(
        format_ticket_assist_snapshot(ticket=ticket_details, snapshot=snapshot),
        reply_markup=build_ticket_assist_markup(
            ticket_public_id=ticket_details.public_id,
            summary_status=snapshot.summary_status,
            suggested_macro_ids=tuple(
                (item.macro_id, item.title) for item in snapshot.macro_suggestions
            ),
        ),
    )
