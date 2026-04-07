from __future__ import annotations

from collections.abc import Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from application.use_cases.tickets.summaries import OperatorSummary
from bot.callbacks import AdminOperatorCallback
from bot.formatters.operator import format_operator_button_text


def build_operator_management_markup(
    *,
    operators: Sequence[OperatorSummary],
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for operator in operators:
        builder.row(
            _build_callback_button(
                format_operator_button_text(operator),
                AdminOperatorCallback(
                    action="view",
                    telegram_user_id=operator.telegram_user_id,
                ).pack(),
            )
        )

    builder.row(
        _build_callback_button(
            "Добавить",
            AdminOperatorCallback(action="add", telegram_user_id=0).pack(),
        ),
        _build_callback_button(
            "Обновить",
            AdminOperatorCallback(action="refresh", telegram_user_id=0).pack(),
        )
    )
    return builder.as_markup()


def build_operator_detail_markup(
    *,
    telegram_user_id: int,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        _build_callback_button(
            "Снять роль",
            AdminOperatorCallback(
                action="revoke",
                telegram_user_id=telegram_user_id,
            ).pack(),
        )
    )
    builder.row(
        _build_callback_button(
            "К списку",
            AdminOperatorCallback(
                action="back_list",
                telegram_user_id=telegram_user_id,
            ).pack(),
        )
    )
    return builder.as_markup()


def build_operator_revoke_confirmation_markup(
    *,
    telegram_user_id: int,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        _build_callback_button(
            "Снять роль",
            AdminOperatorCallback(
                action="confirm_revoke",
                telegram_user_id=telegram_user_id,
            ).pack(),
        ),
        _build_callback_button(
            "Назад",
            AdminOperatorCallback(
                action="cancel_revoke",
                telegram_user_id=telegram_user_id,
            ).pack(),
        ),
    )
    return builder.as_markup()


def _build_callback_button(text: str, callback_data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=callback_data)
