from __future__ import annotations

from uuid import UUID

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import MagicData, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from application.services.helpdesk.service import HelpdeskServiceFactory
from application.use_cases.tickets.summaries import TicketFeedbackMutationStatus
from bot.callbacks import ClientFeedbackCallback
from bot.handlers.operator.parsers import parse_ticket_public_id
from bot.handlers.user.states import UserFeedbackStates
from bot.keyboards.inline.feedback import build_ticket_feedback_comment_markup
from bot.texts.common import CHAT_RATE_LIMIT_TEXT, SERVICE_UNAVAILABLE_TEXT
from bot.texts.feedback import (
    TICKET_FEEDBACK_ALREADY_SAVED_TEXT,
    TICKET_FEEDBACK_COMMENT_ALREADY_SAVED_TEXT,
    TICKET_FEEDBACK_COMMENT_EMPTY_TEXT,
    TICKET_FEEDBACK_COMMENT_PROMPT_TEXT,
    TICKET_FEEDBACK_COMMENT_SAVED_TEXT,
    TICKET_FEEDBACK_NOT_AVAILABLE_TEXT,
    TICKET_FEEDBACK_SKIPPED_TEXT,
    TICKET_FEEDBACK_STALE_TEXT,
    TICKET_FEEDBACK_THANK_YOU_TEXT,
)
from domain.enums.roles import UserRole
from domain.enums.tickets import TicketStatus
from infrastructure.redis.contracts import ChatRateLimiter, GlobalRateLimiter

router = Router(name="client_feedback")


@router.callback_query(
    MagicData(F.event_user_role == UserRole.USER),
    ClientFeedbackCallback.filter(F.action == "rate"),
)
async def handle_ticket_feedback_rating(
    callback: CallbackQuery,
    callback_data: ClientFeedbackCallback,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
) -> None:
    ticket_public_id = _parse_feedback_ticket_id(callback_data.ticket_public_id)
    if ticket_public_id is None or callback_data.rating not in {1, 2, 3, 4, 5}:
        await callback.answer(TICKET_FEEDBACK_STALE_TEXT, show_alert=True)
        return
    if not await global_rate_limiter.allow():
        await callback.answer(SERVICE_UNAVAILABLE_TEXT, show_alert=True)
        return

    async with helpdesk_service_factory() as helpdesk_service:
        result = await helpdesk_service.submit_ticket_feedback_rating(
            ticket_public_id=ticket_public_id,
            client_chat_id=callback.from_user.id,
            rating=callback_data.rating,
        )

    if result.status == TicketFeedbackMutationStatus.CREATED:
        await _try_clear_feedback_markup(callback)
        if isinstance(callback.message, Message):
            await callback.message.answer(
                TICKET_FEEDBACK_THANK_YOU_TEXT,
                reply_markup=build_ticket_feedback_comment_markup(
                    ticket_public_id=ticket_public_id
                ),
            )
        await callback.answer()
        return

    if result.status == TicketFeedbackMutationStatus.ALREADY_RECORDED:
        await callback.answer(TICKET_FEEDBACK_ALREADY_SAVED_TEXT, show_alert=True)
        return
    if result.status == TicketFeedbackMutationStatus.NOT_CLOSED:
        await callback.answer(TICKET_FEEDBACK_NOT_AVAILABLE_TEXT, show_alert=True)
        return
    await callback.answer(TICKET_FEEDBACK_STALE_TEXT, show_alert=True)


@router.callback_query(
    MagicData(F.event_user_role == UserRole.USER),
    ClientFeedbackCallback.filter(F.action == "comment"),
)
async def handle_ticket_feedback_comment_prompt(
    callback: CallbackQuery,
    callback_data: ClientFeedbackCallback,
    state: FSMContext,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
) -> None:
    ticket_public_id = _parse_feedback_ticket_id(callback_data.ticket_public_id)
    if ticket_public_id is None:
        await callback.answer(TICKET_FEEDBACK_STALE_TEXT, show_alert=True)
        return
    if not await global_rate_limiter.allow():
        await callback.answer(SERVICE_UNAVAILABLE_TEXT, show_alert=True)
        return

    async with helpdesk_service_factory() as helpdesk_service:
        feedback = await helpdesk_service.get_ticket_feedback(ticket_public_id=ticket_public_id)
        ticket_details = await helpdesk_service.get_ticket_details(
            ticket_public_id=ticket_public_id
        )

    if feedback is None or ticket_details is None:
        await callback.answer(TICKET_FEEDBACK_STALE_TEXT, show_alert=True)
        return
    if ticket_details.status != TicketStatus.CLOSED:
        await callback.answer(TICKET_FEEDBACK_NOT_AVAILABLE_TEXT, show_alert=True)
        return
    if ticket_details.client_chat_id != callback.from_user.id:
        await callback.answer(TICKET_FEEDBACK_STALE_TEXT, show_alert=True)
        return
    if feedback.comment:
        await callback.answer(TICKET_FEEDBACK_COMMENT_ALREADY_SAVED_TEXT, show_alert=True)
        return

    await state.set_state(UserFeedbackStates.writing_comment)
    await state.set_data({"ticket_public_id": str(ticket_public_id)})
    await _replace_feedback_prompt(
        callback=callback,
        text=TICKET_FEEDBACK_COMMENT_PROMPT_TEXT,
    )
    await callback.answer()


@router.callback_query(
    MagicData(F.event_user_role == UserRole.USER),
    ClientFeedbackCallback.filter(F.action == "skip"),
)
async def handle_ticket_feedback_skip(
    callback: CallbackQuery,
    callback_data: ClientFeedbackCallback,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
) -> None:
    ticket_public_id = _parse_feedback_ticket_id(callback_data.ticket_public_id)
    if ticket_public_id is None:
        await callback.answer(TICKET_FEEDBACK_STALE_TEXT, show_alert=True)
        return
    if not await global_rate_limiter.allow():
        await callback.answer(SERVICE_UNAVAILABLE_TEXT, show_alert=True)
        return

    async with helpdesk_service_factory() as helpdesk_service:
        feedback = await helpdesk_service.get_ticket_feedback(ticket_public_id=ticket_public_id)
        ticket_details = await helpdesk_service.get_ticket_details(
            ticket_public_id=ticket_public_id
        )

    if feedback is None or ticket_details is None:
        await callback.answer(TICKET_FEEDBACK_STALE_TEXT, show_alert=True)
        return
    if ticket_details.status != TicketStatus.CLOSED:
        await callback.answer(TICKET_FEEDBACK_NOT_AVAILABLE_TEXT, show_alert=True)
        return
    if ticket_details.client_chat_id != callback.from_user.id:
        await callback.answer(TICKET_FEEDBACK_STALE_TEXT, show_alert=True)
        return

    await _replace_feedback_prompt(
        callback=callback,
        text=TICKET_FEEDBACK_SKIPPED_TEXT,
    )
    await callback.answer()


@router.message(
    StateFilter(UserFeedbackStates.writing_comment),
    MagicData(F.event_user_role == UserRole.USER),
    F.text & ~F.text.startswith("/"),
)
async def handle_ticket_feedback_comment(
    message: Message,
    state: FSMContext,
    helpdesk_service_factory: HelpdeskServiceFactory,
    global_rate_limiter: GlobalRateLimiter,
    chat_rate_limiter: ChatRateLimiter,
) -> None:
    if message.text is None:
        return
    if not await global_rate_limiter.allow():
        await message.answer(SERVICE_UNAVAILABLE_TEXT)
        return
    if not await chat_rate_limiter.allow(chat_id=message.chat.id):
        await message.answer(CHAT_RATE_LIMIT_TEXT)
        return

    comment = message.text.strip()
    if not comment:
        await message.answer(TICKET_FEEDBACK_COMMENT_EMPTY_TEXT)
        return

    state_data = await state.get_data()
    ticket_public_id = _parse_feedback_ticket_id(state_data.get("ticket_public_id"))
    if ticket_public_id is None:
        await state.clear()
        await message.answer(TICKET_FEEDBACK_STALE_TEXT)
        return

    async with helpdesk_service_factory() as helpdesk_service:
        result = await helpdesk_service.add_ticket_feedback_comment(
            ticket_public_id=ticket_public_id,
            client_chat_id=message.chat.id,
            comment=comment,
        )

    if result.status == TicketFeedbackMutationStatus.UPDATED:
        await state.clear()
        await message.answer(TICKET_FEEDBACK_COMMENT_SAVED_TEXT)
        return
    if result.status == TicketFeedbackMutationStatus.ALREADY_RECORDED:
        await state.clear()
        await message.answer(TICKET_FEEDBACK_COMMENT_ALREADY_SAVED_TEXT)
        return

    await state.clear()
    await message.answer(
        TICKET_FEEDBACK_NOT_AVAILABLE_TEXT
        if result.status == TicketFeedbackMutationStatus.NOT_CLOSED
        else TICKET_FEEDBACK_STALE_TEXT
    )


def _parse_feedback_ticket_id(raw_ticket_public_id: str | None) -> UUID | None:
    if raw_ticket_public_id is None:
        return None
    return parse_ticket_public_id(raw_ticket_public_id)


async def _try_clear_feedback_markup(callback: CallbackQuery) -> None:
    if not isinstance(callback.message, Message):
        return
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        return


async def _replace_feedback_prompt(
    *,
    callback: CallbackQuery,
    text: str,
) -> None:
    if not isinstance(callback.message, Message):
        return
    try:
        await callback.message.edit_text(text, reply_markup=None)
    except TelegramBadRequest:
        await callback.message.answer(text)
