from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from application.use_cases.tickets.summaries import TagSummary
from bot.callbacks import OperatorTagCallback
from bot.formatters.operator import format_tag_button_text


def build_ticket_tags_markup(
    *,
    ticket_public_id: UUID,
    available_tags: Sequence[TagSummary],
    active_tag_names: Sequence[str],
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    callback_value = str(ticket_public_id)
    active_set = set(active_tag_names)

    for tag in available_tags:
        builder.row(
            _button(
                format_tag_button_text(tag, selected=tag.name in active_set),
                OperatorTagCallback(
                    action="toggle",
                    ticket_public_id=callback_value,
                    tag_id=tag.id,
                ).pack(),
            )
        )

    builder.row(
        _button(
            "К заявке",
            OperatorTagCallback(
                action="ticket",
                ticket_public_id=callback_value,
                tag_id=0,
            ).pack(),
        )
    )
    return builder.as_markup()


def _button(text: str, callback_data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=callback_data)
