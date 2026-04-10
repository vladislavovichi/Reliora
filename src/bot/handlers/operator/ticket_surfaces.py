from __future__ import annotations

from aiogram.types import CallbackQuery, Message

from application.use_cases.tickets.summaries import TicketDetailsSummary
from bot.formatters.operator_ticket_views import (
    format_active_ticket_context,
    format_ticket_details,
    format_ticket_history_chunks,
    format_ticket_notes_chunks,
    format_ticket_notes_text,
)
from bot.keyboards.inline.operator_actions import (
    build_ticket_actions_markup,
    build_ticket_notes_markup,
)


def format_ticket_main_surface(
    ticket_details: TicketDetailsSummary,
    *,
    is_active_context: bool = False,
) -> str:
    if is_active_context:
        return format_active_ticket_context(ticket_details)
    return format_ticket_details(ticket_details)


async def send_ticket_details(
    *,
    message: Message,
    ticket_details: TicketDetailsSummary,
    include_history: bool = False,
    is_active_context: bool = False,
) -> None:
    await message.answer(
        format_ticket_main_surface(ticket_details, is_active_context=is_active_context),
        reply_markup=build_ticket_actions_markup(
            ticket_public_id=ticket_details.public_id,
            status=ticket_details.status,
        ),
    )
    if not include_history:
        return

    for chunk in format_ticket_history_chunks(ticket_details):
        await message.answer(chunk)


async def edit_ticket_main_surface(
    *,
    callback: CallbackQuery,
    ticket_details: TicketDetailsSummary,
    answer_text: str,
    is_active_context: bool = False,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer(answer_text)
        return

    await callback.answer(answer_text)
    await edit_ticket_main_message(
        message=callback.message,
        ticket_details=ticket_details,
        is_active_context=is_active_context,
    )


async def edit_ticket_main_message(
    *,
    message: Message,
    ticket_details: TicketDetailsSummary,
    is_active_context: bool = False,
) -> None:
    await message.edit_text(
        format_ticket_main_surface(ticket_details, is_active_context=is_active_context),
        reply_markup=build_ticket_actions_markup(
            ticket_public_id=ticket_details.public_id,
            status=ticket_details.status,
        ),
    )


async def send_ticket_notes(
    *,
    message: Message,
    ticket_details: TicketDetailsSummary,
) -> None:
    await message.answer(
        format_ticket_notes_text(ticket_details),
        reply_markup=build_ticket_notes_markup(ticket_public_id=ticket_details.public_id),
    )
    for chunk in format_ticket_notes_chunks(ticket_details):
        await message.answer(chunk)
