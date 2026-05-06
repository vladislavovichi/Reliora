from __future__ import annotations

from collections.abc import Sequence

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from application.contracts.runtime import (
    GlobalRateLimiter,
    OperatorActiveTicketStore,
    OperatorPresenceHelper,
    TicketLiveSessionStore,
    TicketLockManager,
)
from application.use_cases.tickets.summaries import TagSummary, TicketTagsSummary
from backend.grpc.contracts import HelpdeskBackendClientFactory
from bot.adapters.helpdesk import build_request_actor
from bot.callbacks import OperatorActionCallback, OperatorTagCallback
from bot.formatters.operator_admin_views import format_ticket_tags_response
from bot.handlers.operator.active_context import activate_ticket_for_operator
from bot.handlers.operator.common import respond_to_operator
from bot.handlers.operator.parsers import parse_ticket_public_id
from bot.handlers.operator.ticket_surfaces import edit_ticket_main_surface
from bot.keyboards.inline.tags import build_ticket_tags_markup
from bot.texts.common import (
    INVALID_TICKET_ID_TEXT,
    SERVICE_UNAVAILABLE_TEXT,
    TICKET_LOCKED_TEXT,
    TICKET_NOT_FOUND_TEXT,
)
from bot.texts.operator import (
    TAG_ACTION_STALE_TEXT,
    TAGS_OPENED_TEXT,
    TAGS_UPDATED_TEXT,
    build_active_ticket_opened_text,
    build_view_opened_text,
)

router = Router(name="operator_tags")


@router.callback_query(OperatorActionCallback.filter(F.action == "tags"))
async def handle_open_tags(
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
        ticket_tags = await helpdesk_backend.list_ticket_tags(
            ticket_public_id=ticket_public_id,
            actor=build_request_actor(callback.from_user),
        )
        available_tags = await helpdesk_backend.list_available_tags(
            actor=build_request_actor(callback.from_user),
        )

    if ticket_tags is None:
        await respond_to_operator(callback, TICKET_NOT_FOUND_TEXT)
        return

    async with helpdesk_backend_client_factory() as helpdesk_backend:
        ticket_details = await helpdesk_backend.get_ticket_details(
            ticket_public_id=ticket_public_id,
            actor=build_request_actor(callback.from_user),
        )
    if ticket_details is not None:
        await activate_ticket_for_operator(
            active_ticket_store=operator_active_ticket_store,
            operator_telegram_user_id=callback.from_user.id,
            ticket_details=ticket_details,
            ticket_live_session_store=ticket_live_session_store,
        )
    await _edit_ticket_tags_surface(
        callback=callback,
        ticket_tags=ticket_tags,
        available_tags=available_tags,
        answer_text=TAGS_OPENED_TEXT,
    )


@router.callback_query(OperatorTagCallback.filter(F.action == "toggle"))
async def handle_toggle_tag(
    callback: CallbackQuery,
    callback_data: OperatorTagCallback,
    helpdesk_backend_client_factory: HelpdeskBackendClientFactory,
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
        async with helpdesk_backend_client_factory() as helpdesk_backend:
            ticket_tags = await helpdesk_backend.list_ticket_tags(
                ticket_public_id=ticket_public_id,
                actor=build_request_actor(callback.from_user),
            )
            available_tags = await helpdesk_backend.list_available_tags(
                actor=build_request_actor(callback.from_user),
            )
            tag = _find_tag(available_tags, callback_data.tag_id)
            if ticket_tags is None:
                await respond_to_operator(callback, TICKET_NOT_FOUND_TEXT)
                return
            if tag is None:
                await _edit_ticket_tags_surface(
                    callback=callback,
                    ticket_tags=ticket_tags,
                    available_tags=available_tags,
                    answer_text=TAG_ACTION_STALE_TEXT,
                )
                return

            if tag.name in ticket_tags.tags:
                await helpdesk_backend.remove_tag_from_ticket(
                    ticket_public_id=ticket_public_id,
                    tag_name=tag.name,
                    actor=build_request_actor(callback.from_user),
                )
            else:
                await helpdesk_backend.add_tag_to_ticket(
                    ticket_public_id=ticket_public_id,
                    tag_name=tag.name,
                    actor=build_request_actor(callback.from_user),
                )

            refreshed_tags = await helpdesk_backend.list_ticket_tags(
                ticket_public_id=ticket_public_id,
                actor=build_request_actor(callback.from_user),
            )
            refreshed_available_tags = await helpdesk_backend.list_available_tags(
                actor=build_request_actor(callback.from_user),
            )
    finally:
        await lock.release()

    if refreshed_tags is None:
        await respond_to_operator(callback, TICKET_NOT_FOUND_TEXT)
        return

    async with helpdesk_backend_client_factory() as helpdesk_backend:
        ticket_details = await helpdesk_backend.get_ticket_details(
            ticket_public_id=ticket_public_id,
            actor=build_request_actor(callback.from_user),
        )
    if ticket_details is not None:
        await activate_ticket_for_operator(
            active_ticket_store=operator_active_ticket_store,
            operator_telegram_user_id=callback.from_user.id,
            ticket_details=ticket_details,
            ticket_live_session_store=ticket_live_session_store,
        )
    await _edit_ticket_tags_surface(
        callback=callback,
        ticket_tags=refreshed_tags,
        available_tags=refreshed_available_tags,
        answer_text=TAGS_UPDATED_TEXT,
    )


@router.callback_query(OperatorTagCallback.filter(F.action == "ticket"))
async def handle_back_to_ticket(
    callback: CallbackQuery,
    callback_data: OperatorTagCallback,
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


async def _edit_ticket_tags_surface(
    *,
    callback: CallbackQuery,
    ticket_tags: TicketTagsSummary,
    available_tags: Sequence[TagSummary],
    answer_text: str,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer(answer_text)
        return
    await callback.answer(answer_text)
    await callback.message.edit_text(
        format_ticket_tags_response(ticket_tags.public_number, ticket_tags.tags, available_tags),
        reply_markup=build_ticket_tags_markup(
            ticket_public_id=ticket_tags.public_id,
            available_tags=available_tags,
            active_tag_names=ticket_tags.tags,
        ),
    )


def _find_tag(
    available_tags: Sequence[TagSummary],
    tag_id: int,
) -> TagSummary | None:
    return next((tag for tag in available_tags if tag.id == tag_id), None)
