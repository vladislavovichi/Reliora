from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from application.use_cases.tickets.summaries import MacroSummary
from bot.callbacks import AdminMacroCallback, OperatorMacroCallback
from bot.formatters.operator import format_macro_button_text


def build_operator_macro_picker_markup(
    *,
    ticket_public_id: UUID,
    macros: Sequence[MacroSummary],
    current_page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    callback_value = str(ticket_public_id)

    for macro in macros:
        builder.row(
            _button(
                format_macro_button_text(macro),
                OperatorMacroCallback(
                    action="preview",
                    ticket_public_id=callback_value,
                    macro_id=macro.id,
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
                    OperatorMacroCallback(
                        action="page",
                        ticket_public_id=callback_value,
                        macro_id=0,
                        page=current_page - 1,
                    ).pack(),
                )
            )
        row.append(
            _button(
                f"{current_page} / {total_pages}",
                OperatorMacroCallback(
                    action="noop",
                    ticket_public_id=callback_value,
                    macro_id=0,
                    page=current_page,
                ).pack(),
            )
        )
        if current_page < total_pages:
            row.append(
                _button(
                    "Далее ›",
                    OperatorMacroCallback(
                        action="page",
                        ticket_public_id=callback_value,
                        macro_id=0,
                        page=current_page + 1,
                    ).pack(),
                )
            )
        builder.row(*row)

    builder.row(
        _button(
            "Назад",
            OperatorMacroCallback(
                action="ticket",
                ticket_public_id=callback_value,
                macro_id=0,
                page=current_page,
            ).pack(),
        )
    )
    return builder.as_markup()


def build_operator_macro_preview_markup(
    *,
    ticket_public_id: UUID,
    macro_id: int,
    page: int,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    callback_value = str(ticket_public_id)
    builder.row(
        _button(
            "Отправить",
            OperatorMacroCallback(
                action="apply",
                ticket_public_id=callback_value,
                macro_id=macro_id,
                page=page,
            ).pack(),
        ),
        _button(
            "Назад",
            OperatorMacroCallback(
                action="back",
                ticket_public_id=callback_value,
                macro_id=macro_id,
                page=page,
            ).pack(),
        ),
    )
    return builder.as_markup()


def build_admin_macro_list_markup(
    *,
    macros: Sequence[MacroSummary],
    current_page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for macro in macros:
        builder.row(
            _button(
                format_macro_button_text(macro),
                AdminMacroCallback(action="view", macro_id=macro.id, page=current_page).pack(),
            )
        )

    if total_pages > 1:
        row: list[InlineKeyboardButton] = []
        if current_page > 1:
            row.append(
                _button(
                    "‹ Назад",
                    AdminMacroCallback(action="page", macro_id=0, page=current_page - 1).pack(),
                )
            )
        row.append(
            _button(
                f"{current_page} / {total_pages}",
                AdminMacroCallback(action="noop", macro_id=0, page=current_page).pack(),
            )
        )
        if current_page < total_pages:
            row.append(
                _button(
                    "Далее ›",
                    AdminMacroCallback(action="page", macro_id=0, page=current_page + 1).pack(),
                )
            )
        builder.row(*row)

    builder.row(
        _button(
            "Новый",
            AdminMacroCallback(action="create", macro_id=0, page=current_page).pack(),
        )
    )
    return builder.as_markup()


def build_admin_macro_detail_markup(*, macro_id: int, page: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        _button(
            "Название",
            AdminMacroCallback(action="edit_title", macro_id=macro_id, page=page).pack(),
        )
    )
    builder.row(
        _button(
            "Текст",
            AdminMacroCallback(action="edit_body", macro_id=macro_id, page=page).pack(),
        )
    )
    builder.row(
        _button(
            "Удалить",
            AdminMacroCallback(action="delete", macro_id=macro_id, page=page).pack(),
        ),
        _button(
            "Назад",
            AdminMacroCallback(action="back_list", macro_id=macro_id, page=page).pack(),
        ),
    )
    return builder.as_markup()


def build_admin_macro_delete_markup(*, macro_id: int, page: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        _button(
            "Удалить",
            AdminMacroCallback(action="confirm_delete", macro_id=macro_id, page=page).pack(),
        ),
        _button(
            "Назад",
            AdminMacroCallback(action="cancel_delete", macro_id=macro_id, page=page).pack(),
        ),
    )
    return builder.as_markup()


def build_admin_macro_create_preview_markup(*, page: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        _button(
            "Сохранить",
            AdminMacroCallback(action="preview_save", macro_id=0, page=page).pack(),
        ),
        _button(
            "Изменить",
            AdminMacroCallback(action="preview_edit", macro_id=0, page=page).pack(),
        ),
    )
    builder.row(
        _button(
            "Отмена",
            AdminMacroCallback(action="preview_cancel", macro_id=0, page=page).pack(),
        )
    )
    return builder.as_markup()


def _button(text: str, callback_data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=callback_data)
