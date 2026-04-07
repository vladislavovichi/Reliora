from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from application.use_cases.tickets.summaries import (
    MacroSummary,
    OperatorTicketSummary,
    QueuedTicketSummary,
)
from bot.callbacks import OperatorActionCallback, OperatorMacroCallback, OperatorQueueCallback
from bot.formatters.operator import format_macro_button_text
from domain.enums.tickets import TicketStatus


def build_ticket_actions_markup(
    *,
    ticket_public_id: UUID,
    status: TicketStatus,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    callback_value = str(ticket_public_id)

    first_row: list[tuple[str, str]] = []
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
        first_row.append(
            (
                "Макросы",
                OperatorActionCallback(action="macros", ticket_public_id=callback_value).pack(),
            )
        )
    if first_row:
        builder.row(*[_build_callback_button(text, data) for text, data in first_row])

    second_row: list[tuple[str, str]] = []
    if status != TicketStatus.CLOSED:
        second_row.append(
            (
                "Метки",
                OperatorActionCallback(action="tags", ticket_public_id=callback_value).pack(),
            )
        )
    if status != TicketStatus.CLOSED:
        second_row.append(
            (
                "Передать",
                OperatorActionCallback(action="reassign", ticket_public_id=callback_value).pack(),
            )
        )
    if second_row:
        builder.row(*[_build_callback_button(text, data) for text, data in second_row])

    third_row: list[tuple[str, str]] = []
    if status in {TicketStatus.QUEUED, TicketStatus.ASSIGNED}:
        third_row.append(
            (
                "Эскалация",
                OperatorActionCallback(action="escalate", ticket_public_id=callback_value).pack(),
            )
        )
    if status != TicketStatus.CLOSED:
        third_row.append(
            (
                "Закрыть",
                OperatorActionCallback(action="close", ticket_public_id=callback_value).pack(),
            )
        )
    if third_row:
        builder.row(*[_build_callback_button(text, data) for text, data in third_row])

    return builder.as_markup()


def build_ticket_list_markup(
    *,
    tickets: Sequence[QueuedTicketSummary | OperatorTicketSummary],
    scope: str,
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
