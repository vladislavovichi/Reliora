from __future__ import annotations

from collections.abc import Sequence
from typing import Literal
from uuid import UUID

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from application.use_cases.tickets.summaries import (
    MacroSummary,
    OperatorTicketSummary,
    QueuedTicketSummary,
)
from bot.callbacks import OperatorActionCallback, OperatorMacroCallback, OperatorQueueCallback
from bot.formatters.operator_primitives import format_macro_button_text
from bot.texts.buttons import BACK_BUTTON_TEXT, CLOSE_BUTTON_TEXT, OPEN_BUTTON_TEXT
from domain.enums.tickets import TicketStatus


def build_ticket_actions_markup(
    *,
    ticket_public_id: UUID,
    status: TicketStatus,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    callback_value = str(ticket_public_id)

    if status == TicketStatus.QUEUED:
        builder.row(
            _build_callback_button(
                "Взять",
                OperatorActionCallback(action="take", ticket_public_id=callback_value).pack(),
            ),
            _build_callback_button(
                "Ещё",
                OperatorActionCallback(action="more", ticket_public_id=callback_value).pack(),
            ),
        )
        return builder.as_markup()

    if status in {TicketStatus.ASSIGNED, TicketStatus.ESCALATED}:
        builder.row(
            _build_callback_button(
                CLOSE_BUTTON_TEXT,
                OperatorActionCallback(action="close", ticket_public_id=callback_value).pack(),
            ),
            _build_callback_button(
                "Макросы",
                OperatorActionCallback(action="macros", ticket_public_id=callback_value).pack(),
            ),
            _build_callback_button(
                "Ещё",
                OperatorActionCallback(action="more", ticket_public_id=callback_value).pack(),
            ),
        )

    return builder.as_markup()


def build_ticket_more_actions_markup(
    *,
    ticket_public_id: UUID,
    status: TicketStatus,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    callback_value = str(ticket_public_id)

    change_row: list[InlineKeyboardButton] = []
    if status != TicketStatus.CLOSED:
        change_row.append(
            _build_callback_button(
                "Метки",
                OperatorActionCallback(action="tags", ticket_public_id=callback_value).pack(),
            )
        )

    if status in {TicketStatus.ASSIGNED, TicketStatus.ESCALATED}:
        change_row.append(
            _build_callback_button(
                "Передать",
                OperatorActionCallback(action="reassign", ticket_public_id=callback_value).pack(),
            )
        )
    if change_row:
        builder.row(*change_row)

    builder.row(
        _build_callback_button(
            "Экспорт",
            OperatorActionCallback(action="export", ticket_public_id=callback_value).pack(),
        )
    )

    status_row: list[InlineKeyboardButton] = []
    if status in {TicketStatus.QUEUED, TicketStatus.ASSIGNED}:
        status_row.append(
            _build_callback_button(
                "Эскалация",
                OperatorActionCallback(action="escalate", ticket_public_id=callback_value).pack(),
            )
        )

    status_row.append(
        _build_callback_button(
            "Карточка",
            OperatorActionCallback(action="card", ticket_public_id=callback_value).pack(),
        )
    )
    builder.row(*status_row)
    builder.row(
        _build_callback_button(
            BACK_BUTTON_TEXT,
            OperatorActionCallback(action="back", ticket_public_id=callback_value).pack(),
        )
    )
    return builder.as_markup()


def build_ticket_export_actions_markup(*, ticket_public_id: UUID) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    callback_value = str(ticket_public_id)
    builder.row(
        _build_callback_button(
            "CSV",
            OperatorActionCallback(action="export_csv", ticket_public_id=callback_value).pack(),
        ),
        _build_callback_button(
            "HTML",
            OperatorActionCallback(action="export_html", ticket_public_id=callback_value).pack(),
        ),
    )
    builder.row(
        _build_callback_button(
            BACK_BUTTON_TEXT,
            OperatorActionCallback(action="more", ticket_public_id=callback_value).pack(),
        )
    )
    return builder.as_markup()


def build_ticket_switch_markup(*, ticket_public_id: UUID) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        _build_callback_button(
            OPEN_BUTTON_TEXT,
            OperatorActionCallback(action="view", ticket_public_id=str(ticket_public_id)).pack(),
        )
    )
    return builder.as_markup()


def build_ticket_list_markup(
    *,
    tickets: Sequence[QueuedTicketSummary | OperatorTicketSummary],
    scope: Literal["queue", "mine"],
    current_page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for ticket in tickets:
        callback_value = str(ticket.public_id)
        builder.row(
            _build_callback_button(
                ticket.public_number,
                OperatorActionCallback(action="view", ticket_public_id=callback_value).pack(),
            ),
        )

    if total_pages > 1:
        pagination_row: list[InlineKeyboardButton] = []
        if current_page > 1:
            pagination_row.append(
                _build_callback_button(
                    "‹ Назад",
                    OperatorQueueCallback(
                        action="page",
                        scope=scope,
                        page=current_page - 1,
                    ).pack(),
                )
            )

        pagination_row.append(
            _build_callback_button(
                f"{current_page} / {total_pages}",
                OperatorQueueCallback(
                    action="noop",
                    scope=scope,
                    page=current_page,
                ).pack(),
            )
        )

        if current_page < total_pages:
            pagination_row.append(
                _build_callback_button(
                    "Далее ›",
                    OperatorQueueCallback(
                        action="page",
                        scope=scope,
                        page=current_page + 1,
                    ).pack(),
                )
            )

        builder.row(*pagination_row)

    return builder.as_markup()


def build_queue_markup(
    *,
    tickets: Sequence[QueuedTicketSummary],
    current_page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    return build_ticket_list_markup(
        tickets=tickets,
        scope="queue",
        current_page=current_page,
        total_pages=total_pages,
    )


def build_operator_ticket_list_markup(
    *,
    tickets: Sequence[OperatorTicketSummary],
    current_page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    return build_ticket_list_markup(
        tickets=tickets,
        scope="mine",
        current_page=current_page,
        total_pages=total_pages,
    )


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
                    action="preview",
                    ticket_public_id=callback_value,
                    macro_id=macro.id,
                    page=1,
                ).pack(),
            )
        )
    return builder.as_markup()


def _build_callback_button(text: str, callback_data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=callback_data)
