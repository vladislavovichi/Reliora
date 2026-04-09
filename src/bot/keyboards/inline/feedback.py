from __future__ import annotations

from uuid import UUID

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.callbacks import ClientFeedbackCallback
from bot.texts.buttons import COMMENT_BUTTON_TEXT, SKIP_BUTTON_TEXT


def build_ticket_feedback_rating_markup(*, ticket_public_id: UUID) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    callback_value = str(ticket_public_id)
    builder.row(
        *(
            _button(
                str(rating),
                ClientFeedbackCallback(
                    action="rate",
                    ticket_public_id=callback_value,
                    rating=rating,
                ).pack(),
            )
            for rating in range(1, 6)
        )
    )
    return builder.as_markup()


def build_ticket_feedback_comment_markup(*, ticket_public_id: UUID) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    callback_value = str(ticket_public_id)
    builder.row(
        _button(
            COMMENT_BUTTON_TEXT,
            ClientFeedbackCallback(
                action="comment",
                ticket_public_id=callback_value,
                rating=0,
            ).pack(),
        ),
        _button(
            SKIP_BUTTON_TEXT,
            ClientFeedbackCallback(
                action="skip",
                ticket_public_id=callback_value,
                rating=0,
            ).pack(),
        ),
    )
    return builder.as_markup()


def _button(text: str, callback_data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=callback_data)
