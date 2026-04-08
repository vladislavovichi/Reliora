from __future__ import annotations

from collections.abc import Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from application.use_cases.tickets.summaries import TicketCategorySummary
from bot.callbacks import AdminCategoryCallback, ClientIntakeCallback
from bot.texts.buttons import BACK_BUTTON_TEXT, CANCEL_BUTTON_TEXT


def build_client_intake_categories_markup(
    categories: Sequence[TicketCategorySummary],
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for category in categories:
        builder.row(
            _button(
                category.title,
                ClientIntakeCallback(action="pick", category_id=category.id).pack(),
            )
        )
    builder.row(
        _button(
            CANCEL_BUTTON_TEXT,
            ClientIntakeCallback(action="cancel", category_id=0).pack(),
        )
    )
    return builder.as_markup()


def build_client_intake_message_markup() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        _button(
            CANCEL_BUTTON_TEXT,
            ClientIntakeCallback(action="cancel", category_id=0).pack(),
        )
    )
    return builder.as_markup()


def build_admin_category_list_markup(
    *,
    categories: Sequence[TicketCategorySummary],
    current_page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for category in categories:
        builder.row(
            _button(
                category.title,
                AdminCategoryCallback(
                    action="view",
                    category_id=category.id,
                    page=current_page,
                ).pack(),
            )
        )

    if total_pages > 1:
        row: list[InlineKeyboardButton] = []
        if current_page > 1:
            row.append(
                _button(
                    "‹ Назад",
                    AdminCategoryCallback(
                        action="page",
                        category_id=0,
                        page=current_page - 1,
                    ).pack(),
                )
            )
        row.append(
            _button(
                f"{current_page} / {total_pages}",
                AdminCategoryCallback(action="noop", category_id=0, page=current_page).pack(),
            )
        )
        if current_page < total_pages:
            row.append(
                _button(
                    "Далее ›",
                    AdminCategoryCallback(
                        action="page",
                        category_id=0,
                        page=current_page + 1,
                    ).pack(),
                )
            )
        builder.row(*row)

    builder.row(
        _button(
            "Новая",
            AdminCategoryCallback(action="create", category_id=0, page=current_page).pack(),
        )
    )
    return builder.as_markup()


def build_admin_category_detail_markup(
    *,
    category: TicketCategorySummary,
    page: int,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        _button(
            "Название",
            AdminCategoryCallback(
                action="edit_title",
                category_id=category.id,
                page=page,
            ).pack(),
        )
    )
    builder.row(
        _button(
            "Скрыть" if category.is_active else "Включить",
            AdminCategoryCallback(
                action="disable" if category.is_active else "enable",
                category_id=category.id,
                page=page,
            ).pack(),
        )
    )
    builder.row(
        _button(
            BACK_BUTTON_TEXT,
            AdminCategoryCallback(
                action="back_list",
                category_id=category.id,
                page=page,
            ).pack(),
        )
    )
    return builder.as_markup()


def _button(text: str, callback_data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=callback_data)
