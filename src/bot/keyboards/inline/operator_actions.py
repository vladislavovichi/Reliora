from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from application.use_cases.tickets import MacroSummary
from bot.callbacks import OperatorActionCallback, OperatorMacroCallback
from bot.formatters.operator import format_macro_button_text
from domain.enums.tickets import TicketStatus


def build_ticket_actions_markup(
    *,
    ticket_public_id: UUID,
    status: TicketStatus,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    callback_value = str(ticket_public_id)

    first_row = [
        (
            "Открыть",
            OperatorActionCallback(action="view", ticket_public_id=callback_value).pack(),
        )
    ]
    if status == TicketStatus.QUEUED:
        first_row.append(
            (
                "Взять",
                OperatorActionCallback(action="take", ticket_public_id=callback_value).pack(),
            )
        )
    elif status in {TicketStatus.ASSIGNED, TicketStatus.ESCALATED}:
        first_row.append(
            (
                "Ответить",
                OperatorActionCallback(action="reply", ticket_public_id=callback_value).pack(),
            )
        )
    builder.row(*[_build_callback_button(text, data) for text, data in first_row])

    second_row: list[tuple[str, str]] = []
    if status in {TicketStatus.QUEUED, TicketStatus.ASSIGNED}:
        second_row.append(
            (
                "Эскалировать",
                OperatorActionCallback(action="escalate", ticket_public_id=callback_value).pack(),
            )
        )
    if status != TicketStatus.CLOSED:
        second_row.append(
            (
                "Закрыть",
                OperatorActionCallback(action="close", ticket_public_id=callback_value).pack(),
            )
        )
    if second_row:
        builder.row(*[_build_callback_button(text, data) for text, data in second_row])

    if status != TicketStatus.CLOSED:
        builder.row(
            _build_callback_button(
                "Переназначить",
                OperatorActionCallback(action="reassign", ticket_public_id=callback_value).pack(),
            )
        )

    return builder.as_markup()


def build_macro_actions_markup(
    *,
    ticket_public_id: UUID,
    macros: Sequence[MacroSummary],
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    callback_value = str(ticket_public_id)
    for macro in macros:
        builder.row(
            _build_callback_button(
                format_macro_button_text(macro),
                OperatorMacroCallback(
                    ticket_public_id=callback_value,
                    macro_id=macro.id,
                ).pack(),
            )
        )
    return builder.as_markup()


def _build_callback_button(text: str, callback_data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=callback_data)
