from __future__ import annotations

from collections.abc import Sequence

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from application.services.helpdesk.service import HelpdeskServiceFactory
from application.use_cases.tickets.summaries import TagSummary
from bot.callbacks import OperatorActionCallback, OperatorTagCallback
from bot.formatters.operator import (
    format_active_ticket_context,
    format_ticket_details,
    format_ticket_tags_response,
)
from bot.handlers.operator.active_context import activate_ticket_for_operator
from bot.handlers.operator.common import respond_to_operator
from bot.handlers.operator.parsers import parse_ticket_public_id
from bot.keyboards.inline.operator_actions import build_ticket_actions_markup
from bot.keyboards.inline.tags import build_ticket_tags_markup
from bot.texts.common import (
    INVALID_TICKET_ID_TEXT,
    SERVICE_UNAVAILABLE_TEXT,
    TICKET_LOCKED_TEXT,
    TICKET_NOT_FOUND_TEXT,
)
from bot.texts.operator import TAG_ACTION_STALE_TEXT, TAGS_UPDATED_TEXT
from infrastructure.redis.contracts import (
    GlobalRateLimiter,
    OperatorActiveTicketStore,
    OperatorPresenceHelper,
    TicketLiveSessionStore,
    TicketLockManager,
)

router = Router(name="operator_tags")


@router.callback_query(OperatorActionCallback.filter(F.action == "tags"))
async def handle_open_tags(
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
        ticket_tags = await helpdesk_service.list_ticket_tags(
            ticket_public_id=ticket_public_id,
            actor_telegram_user_id=callback.from_user.id,
        )
        available_tags = await helpdesk_service.list_available_tags(
            actor_telegram_user_id=callback.from_user.id,
        )

    if ticket_tags is None:
        await respond_to_operator(callback, TICKET_NOT_FOUND_TEXT)
        return

    async with helpdesk_service_factory() as helpdesk_service:
        ticket_details = await helpdesk_service.get_ticket_details(
            ticket_public_id=ticket_public_id,
            actor_telegram_user_id=callback.from_user.id,
        )
    if ticket_details is not None:
        await activate_ticket_for_operator(
            active_ticket_store=operator_active_ticket_store,
            operator_telegram_user_id=callback.from_user.id,
            ticket_details=ticket_details,
            ticket_live_session_store=ticket_live_session_store,
        )
    if not isinstance(callback.message, Message):
        await callback.answer(TAGS_UPDATED_TEXT)
        return

    await callback.answer(TAGS_UPDATED_TEXT)
    await callback.message.edit_text(
        format_ticket_tags_response(
            ticket_tags.public_number,
            ticket_tags.tags,
            available_tags,
        ),
        reply_markup=build_ticket_tags_markup(
            ticket_public_id=ticket_tags.public_id,
            available_tags=available_tags,
            active_tag_names=ticket_tags.tags,
        ),
    )


@router.callback_query(OperatorTagCallback.filter(F.action == "toggle"))
async def handle_toggle_tag(
    callback: CallbackQuery,
    callback_data: OperatorTagCallback,
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

    try:
        async with helpdesk_service_factory() as helpdesk_service:
            ticket_tags = await helpdesk_service.list_ticket_tags(
                ticket_public_id=ticket_public_id,
                actor_telegram_user_id=callback.from_user.id,
            )
            available_tags = await helpdesk_service.list_available_tags(
                actor_telegram_user_id=callback.from_user.id,
            )
            tag = _find_tag(available_tags, callback_data.tag_id)
            if ticket_tags is None:
                await respond_to_operator(callback, TICKET_NOT_FOUND_TEXT)
                return
            if tag is None:
                await respond_to_operator(callback, TAG_ACTION_STALE_TEXT)
                return

            if tag.name in ticket_tags.tags:
                await helpdesk_service.remove_tag_from_ticket(
                    ticket_public_id=ticket_public_id,
                    tag_name=tag.name,
                    actor_telegram_user_id=callback.from_user.id,
                )
            else:
                await helpdesk_service.add_tag_to_ticket(
                    ticket_public_id=ticket_public_id,
                    tag_name=tag.name,
                    actor_telegram_user_id=callback.from_user.id,
                )

            refreshed_tags = await helpdesk_service.list_ticket_tags(
                ticket_public_id=ticket_public_id,
                actor_telegram_user_id=callback.from_user.id,
            )
            refreshed_available_tags = await helpdesk_service.list_available_tags(
                actor_telegram_user_id=callback.from_user.id,
            )
    finally:
        await lock.release()

    if refreshed_tags is None:
        await respond_to_operator(callback, TICKET_NOT_FOUND_TEXT)
        return

    async with helpdesk_service_factory() as helpdesk_service:
        ticket_details = await helpdesk_service.get_ticket_details(
            ticket_public_id=ticket_public_id,
            actor_telegram_user_id=callback.from_user.id,
        )
    if ticket_details is not None:
        await activate_ticket_for_operator(
            active_ticket_store=operator_active_ticket_store,
            operator_telegram_user_id=callback.from_user.id,
            ticket_details=ticket_details,
            ticket_live_session_store=ticket_live_session_store,
        )
    if not isinstance(callback.message, Message):
        await callback.answer(TAGS_UPDATED_TEXT)
        return

    await callback.answer(TAGS_UPDATED_TEXT)
    await callback.message.edit_text(
        format_ticket_tags_response(
            refreshed_tags.public_number,
            refreshed_tags.tags,
            refreshed_available_tags,
        ),
        reply_markup=build_ticket_tags_markup(
            ticket_public_id=refreshed_tags.public_id,
            available_tags=refreshed_available_tags,
            active_tag_names=refreshed_tags.tags,
        ),
    )


@router.callback_query(OperatorTagCallback.filter(F.action == "ticket"))
async def handle_back_to_ticket(
    callback: CallbackQuery,
    callback_data: OperatorTagCallback,
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
        await callback.answer(ticket_details.public_number)
        return

    await callback.answer(ticket_details.public_number)
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


def _find_tag(
    available_tags: Sequence[TagSummary],
    tag_id: int,
) -> TagSummary | None:
    return next((tag for tag in available_tags if tag.id == tag_id), None)
