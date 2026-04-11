from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.callbacks import OperatorInviteCallback
from bot.texts.buttons import BACK_BUTTON_TEXT


def build_operator_invite_confirmation_markup() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="Подтвердить",
            callback_data=OperatorInviteCallback(action="confirm").pack(),
        ),
        InlineKeyboardButton(
            text=BACK_BUTTON_TEXT,
            callback_data=OperatorInviteCallback(action="edit").pack(),
        ),
    )
    return builder.as_markup()
