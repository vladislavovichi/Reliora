from __future__ import annotations

from uuid import UUID

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.callbacks import ClientTicketCallback


def build_client_ticket_markup(*, ticket_public_id: UUID) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        _button(
            "Завершить обращение",
            ClientTicketCallback(
                action="finish",
                ticket_public_id=str(ticket_public_id),
            ).pack(),
        )
    )
    return builder.as_markup()


def build_client_ticket_finish_confirmation_markup(*, ticket_public_id: UUID) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    callback_value = str(ticket_public_id)
    builder.row(
        _button(
            "Завершить",
            ClientTicketCallback(
                action="finish_confirm",
                ticket_public_id=callback_value,
            ).pack(),
        ),
        _button(
            "Продолжить",
            ClientTicketCallback(
                action="finish_cancel",
                ticket_public_id=callback_value,
            ).pack(),
        ),
    )
    return builder.as_markup()


def _button(text: str, callback_data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=callback_data)
