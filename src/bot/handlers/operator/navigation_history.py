from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from application.contracts.actors import RequestActor
from application.use_cases.tickets.archive_browser import (
    ALL_ARCHIVE_CATEGORIES_ID,
    ArchiveBrowserPage,
    build_archive_browser_page,
)
from application.use_cases.tickets.summaries import HistoricalTicketSummary
from backend.grpc.contracts import HelpdeskBackendClientFactory
from bot.adapters.helpdesk import build_request_actor
from bot.callbacks import OperatorArchiveCallback
from bot.formatters.operator_archive_views import (
    ARCHIVE_PAGE_CHUNK,
    format_archive_page,
    format_archive_topic_picker,
    format_archived_ticket_surface,
)
from bot.handlers.operator.common import respond_to_operator
from bot.handlers.operator.parsers import parse_ticket_public_id
from bot.keyboards.inline.operator_history import (
    build_archive_markup,
    build_archive_topic_picker_markup,
    build_archived_ticket_markup,
)
from bot.texts.buttons import ARCHIVE_BUTTON_TEXT
from bot.texts.common import INVALID_TICKET_ID_TEXT, SERVICE_UNAVAILABLE_TEXT, TICKET_NOT_FOUND_TEXT
from bot.texts.operator import (
    ARCHIVE_EMPTY_TEXT,
    build_archive_page_callback_text,
    build_archive_topic_picker_opened_text,
    build_archived_ticket_opened_text,
)
from infrastructure.redis.contracts import GlobalRateLimiter, OperatorPresenceHelper

router = Router(name="operator_navigation_history")


@router.message(F.text == ARCHIVE_BUTTON_TEXT)
async def handle_archive(
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

    tickets = await _load_archived_tickets(
        helpdesk_backend_client_factory=helpdesk_backend_client_factory,
        actor=build_request_actor(message.from_user),
    )
    if not tickets:
        await message.answer(ARCHIVE_EMPTY_TEXT)
        return

    archive_page = build_archive_browser_page(
        tickets=tickets,
        page=1,
        category_id=ALL_ARCHIVE_CATEGORIES_ID,
        page_size=ARCHIVE_PAGE_CHUNK,
    )
    archive_text, archive_markup = build_archive_page_response(archive_page=archive_page)
    await message.answer(archive_text, reply_markup=archive_markup)


@router.callback_query(
    OperatorArchiveCallback.filter(
        F.action.in_({"page", "all", "back", "topic_pick", "topic_back"})
    )
)
async def handle_archive_navigation(
    callback: CallbackQuery,
    callback_data: OperatorArchiveCallback,
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

    tickets = await _load_archived_tickets(
        helpdesk_backend_client_factory=helpdesk_backend_client_factory,
        actor=build_request_actor(callback.from_user),
    )
    if not tickets:
        await respond_to_operator(callback, ARCHIVE_EMPTY_TEXT, ARCHIVE_EMPTY_TEXT)
        return

    target_page = callback_data.page
    target_category_id = callback_data.category_id
    if callback_data.action == "all":
        target_page = 1
        target_category_id = ALL_ARCHIVE_CATEGORIES_ID

    archive_page = build_archive_browser_page(
        tickets=tickets,
        page=target_page,
        category_id=target_category_id,
        page_size=ARCHIVE_PAGE_CHUNK,
    )
    await _edit_archive_page(
        callback=callback,
        archive_page=archive_page,
        answer_text=build_archive_page_callback_text(
            archive_page.current_page,
            category_title=archive_page.selected_category_title,
        ),
    )


@router.callback_query(OperatorArchiveCallback.filter(F.action == "topics"))
async def handle_archive_topic_picker(
    callback: CallbackQuery,
    callback_data: OperatorArchiveCallback,
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

    tickets = await _load_archived_tickets(
        helpdesk_backend_client_factory=helpdesk_backend_client_factory,
        actor=build_request_actor(callback.from_user),
    )
    if not tickets:
        await respond_to_operator(callback, ARCHIVE_EMPTY_TEXT, ARCHIVE_EMPTY_TEXT)
        return

    archive_page = build_archive_browser_page(
        tickets=tickets,
        page=callback_data.page,
        category_id=callback_data.category_id,
        page_size=ARCHIVE_PAGE_CHUNK,
    )
    await _edit_archive_topic_picker(
        callback=callback,
        archive_page=archive_page,
    )


@router.callback_query(OperatorArchiveCallback.filter(F.action == "view"))
async def handle_archived_ticket_view(
    callback: CallbackQuery,
    callback_data: OperatorArchiveCallback,
    helpdesk_backend_client_factory: HelpdeskBackendClientFactory,
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
    async with helpdesk_backend_client_factory() as helpdesk_backend:
        ticket_details = await helpdesk_backend.get_ticket_details(
            ticket_public_id=ticket_public_id,
            actor=build_request_actor(callback.from_user),
        )

    if ticket_details is None:
        await respond_to_operator(callback, TICKET_NOT_FOUND_TEXT)
        return

    if not isinstance(callback.message, Message):
        await callback.answer(build_archived_ticket_opened_text(ticket_details.public_number))
        return

    await callback.answer(build_archived_ticket_opened_text(ticket_details.public_number))
    await callback.message.edit_text(
        format_archived_ticket_surface(ticket_details),
        reply_markup=build_archived_ticket_markup(
            ticket_public_id=str(ticket_details.public_id),
            page=callback_data.page,
            category_id=callback_data.category_id,
        ),
    )


@router.callback_query(OperatorArchiveCallback.filter(F.action == "noop"))
async def handle_archive_noop(
    callback: CallbackQuery,
    callback_data: OperatorArchiveCallback,
    helpdesk_backend_client_factory: HelpdeskBackendClientFactory,
) -> None:
    tickets = await _load_archived_tickets(
        helpdesk_backend_client_factory=helpdesk_backend_client_factory,
        actor=build_request_actor(callback.from_user),
    )
    archive_page = build_archive_browser_page(
        tickets=tickets,
        page=callback_data.page,
        category_id=callback_data.category_id,
        page_size=ARCHIVE_PAGE_CHUNK,
    )
    await callback.answer(
        build_archive_page_callback_text(
            archive_page.current_page,
            category_title=archive_page.selected_category_title,
        )
    )


def build_archive_page_response(
    *,
    archive_page: ArchiveBrowserPage,
) -> tuple[str, InlineKeyboardMarkup]:
    return (
        format_archive_page(
            archive_page.tickets,
            current_page=archive_page.current_page,
            total_pages=archive_page.total_pages,
            selected_category_title=archive_page.selected_category_title,
            total_filtered_tickets=archive_page.total_filtered_tickets,
        ),
        build_archive_markup(
            tickets=archive_page.tickets,
            filters=archive_page.filters,
            current_page=archive_page.current_page,
            total_pages=archive_page.total_pages,
            selected_category_id=archive_page.selected_category_id,
        ),
    )


async def _load_archived_tickets(
    *,
    helpdesk_backend_client_factory: HelpdeskBackendClientFactory,
    actor: RequestActor | None,
) -> tuple[HistoricalTicketSummary, ...]:
    async with helpdesk_backend_client_factory() as helpdesk_backend:
        tickets = await helpdesk_backend.list_archived_tickets(actor=actor)
    return tuple(tickets)


async def _edit_archive_page(
    *,
    callback: CallbackQuery,
    archive_page: ArchiveBrowserPage,
    answer_text: str,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer(answer_text)
        return

    archive_text, archive_markup = build_archive_page_response(archive_page=archive_page)
    await callback.answer(answer_text)
    await callback.message.edit_text(archive_text, reply_markup=archive_markup)


async def _edit_archive_topic_picker(
    *,
    callback: CallbackQuery,
    archive_page: ArchiveBrowserPage,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer(build_archive_topic_picker_opened_text())
        return

    await callback.answer(build_archive_topic_picker_opened_text())
    await callback.message.edit_text(
        format_archive_topic_picker(
            filters=archive_page.filters,
            selected_category_title=archive_page.selected_category_title,
        ),
        reply_markup=build_archive_topic_picker_markup(
            filters=archive_page.filters,
            current_page=archive_page.current_page,
            selected_category_id=archive_page.selected_category_id,
        ),
    )
