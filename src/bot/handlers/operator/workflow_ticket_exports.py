from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, Message

from application.services.helpdesk.service import HelpdeskServiceFactory
from application.use_cases.tickets.exports import TicketReportFormat
from bot.callbacks import OperatorActionCallback
from bot.delivery import deliver_document_to_chat
from bot.formatters.operator_ticket_views import format_ticket_export_actions
from bot.handlers.operator.active_context import activate_ticket_for_operator
from bot.handlers.operator.common import respond_to_operator
from bot.handlers.operator.parsers import parse_ticket_public_id
from bot.keyboards.inline.operator_actions import build_ticket_export_actions_markup
from bot.texts.common import (
    INVALID_TICKET_ID_TEXT,
    SERVICE_UNAVAILABLE_TEXT,
    TICKET_NOT_FOUND_TEXT,
)
from bot.texts.operator import (
    EXPORT_DELIVERY_FAILED_TEXT,
    EXPORT_FAILED_TEXT,
    build_export_opened_text,
    build_export_ready_text,
)
from infrastructure.redis.contracts import (
    GlobalRateLimiter,
    OperatorActiveTicketStore,
    OperatorPresenceHelper,
    TicketLiveSessionStore,
)

router = Router(name="operator_workflow_ticket_exports")
logger = logging.getLogger(__name__)


@router.callback_query(OperatorActionCallback.filter(F.action == "export"))
async def handle_export_action(
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
        await callback.answer(build_export_opened_text(ticket_details.public_number))
        return

    await callback.answer(build_export_opened_text(ticket_details.public_number))
    await callback.message.edit_text(
        format_ticket_export_actions(ticket_details, is_active=is_active_context),
        reply_markup=build_ticket_export_actions_markup(ticket_public_id=ticket_details.public_id),
    )


@router.callback_query(OperatorActionCallback.filter(F.action.in_({"export_csv", "export_html"})))
async def handle_export_file_action(
    callback: CallbackQuery,
    callback_data: OperatorActionCallback,
    bot: Bot,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    operator_presence: OperatorPresenceHelper,
) -> None:
    ticket_public_id = parse_ticket_public_id(callback_data.ticket_public_id)
    if ticket_public_id is None:
        await respond_to_operator(callback, INVALID_TICKET_ID_TEXT)
        return
    if not await global_rate_limiter.allow():
        await respond_to_operator(callback, SERVICE_UNAVAILABLE_TEXT)
        return

    await operator_presence.touch(operator_id=callback.from_user.id)
    export_format = (
        TicketReportFormat.CSV
        if callback_data.action == "export_csv"
        else TicketReportFormat.HTML
    )

    try:
        async with helpdesk_service_factory() as helpdesk_service:
            ticket_export = await helpdesk_service.export_ticket_report(
                ticket_public_id=ticket_public_id,
                format=export_format,
                actor_telegram_user_id=callback.from_user.id,
            )
    except Exception:
        logger.exception(
            "Ticket export failed operator_id=%s ticket_public_id=%s format=%s",
            callback.from_user.id,
            ticket_public_id,
            export_format.value,
        )
        await respond_to_operator(callback, EXPORT_FAILED_TEXT)
        return

    if ticket_export is None:
        await respond_to_operator(callback, TICKET_NOT_FOUND_TEXT)
        return

    delivery_error = await deliver_document_to_chat(
        bot,
        chat_id=callback.from_user.id,
        content=ticket_export.content,
        filename=ticket_export.filename,
        caption=f"Отчёт по заявке {ticket_export.report.public_number}",
        logger=logger,
        operation=f"ticket_report_{export_format.value}",
    )
    if delivery_error is not None:
        logger.warning(
            "Ticket export delivery failed operator_id=%s ticket_public_id=%s format=%s error=%s",
            callback.from_user.id,
            ticket_public_id,
            export_format.value,
            delivery_error,
        )
        await respond_to_operator(callback, EXPORT_DELIVERY_FAILED_TEXT)
        return

    await callback.answer(
        build_export_ready_text(
            ticket_export.report.public_number,
            format_name=export_format.value.upper(),
        )
    )
