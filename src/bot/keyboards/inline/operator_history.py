from __future__ import annotations

from collections.abc import Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from application.use_cases.tickets.archive_browser import (
    ALL_ARCHIVE_CATEGORIES_ID,
    ArchiveCategoryFilter,
)
from application.use_cases.tickets.summaries import HistoricalTicketSummary
from bot.callbacks import OperatorActionCallback, OperatorArchiveCallback
from bot.formatters.operator_primitives import shorten_text


def build_archive_markup(
    *,
    tickets: Sequence[HistoricalTicketSummary],
    filters: Sequence[ArchiveCategoryFilter],
    current_page: int,
    total_pages: int,
    selected_category_id: int,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=_build_all_topics_button_text(selected_category_id),
            callback_data=OperatorArchiveCallback(
                action="all",
                page=1,
                category_id=ALL_ARCHIVE_CATEGORIES_ID,
                ticket_public_id="0",
            ).pack(),
        ),
        InlineKeyboardButton(
            text="Выбрать тему",
            callback_data=OperatorArchiveCallback(
                action="topics",
                page=current_page,
                category_id=selected_category_id,
                ticket_public_id="0",
            ).pack(),
        ),
    )
    if selected_category_id != ALL_ARCHIVE_CATEGORIES_ID:
        selected_filter = next((item for item in filters if item.id == selected_category_id), None)
        if selected_filter is not None:
            builder.row(
                InlineKeyboardButton(
                    text=f"Текущая тема · {shorten_text(selected_filter.title, 20)}",
                    callback_data=OperatorArchiveCallback(
                        action="noop",
                        page=current_page,
                        category_id=selected_category_id,
                        ticket_public_id="0",
                    ).pack(),
                )
            )

    for ticket in tickets:
        builder.row(
            InlineKeyboardButton(
                text=_build_ticket_button_text(ticket),
                callback_data=OperatorArchiveCallback(
                    action="view",
                    page=current_page,
                    category_id=selected_category_id,
                    ticket_public_id=str(ticket.public_id),
                ).pack(),
            )
        )

    if total_pages > 1:
        pagination_row: list[InlineKeyboardButton] = []
        if current_page > 1:
            pagination_row.append(
                InlineKeyboardButton(
                    text="‹ Назад",
                    callback_data=OperatorArchiveCallback(
                        action="page",
                        page=current_page - 1,
                        category_id=selected_category_id,
                        ticket_public_id="0",
                    ).pack(),
                )
            )
        pagination_row.append(
            InlineKeyboardButton(
                text=f"{current_page} / {total_pages}",
                callback_data=OperatorArchiveCallback(
                    action="noop",
                    page=current_page,
                    category_id=selected_category_id,
                    ticket_public_id="0",
                ).pack(),
            )
        )
        if current_page < total_pages:
            pagination_row.append(
                InlineKeyboardButton(
                    text="Далее ›",
                    callback_data=OperatorArchiveCallback(
                        action="page",
                        page=current_page + 1,
                        category_id=selected_category_id,
                        ticket_public_id="0",
                    ).pack(),
                )
            )
        builder.row(*pagination_row)

    return builder.as_markup()


def build_archive_topic_picker_markup(
    *,
    filters: Sequence[ArchiveCategoryFilter],
    current_page: int,
    selected_category_id: int,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for category_filter in filters:
        if category_filter.id == ALL_ARCHIVE_CATEGORIES_ID:
            continue
        builder.row(
            InlineKeyboardButton(
                text=_build_topic_picker_button_text(
                    category_filter=category_filter,
                    selected_category_id=selected_category_id,
                ),
                callback_data=OperatorArchiveCallback(
                    action="topic_pick",
                    page=1,
                    category_id=category_filter.id,
                    ticket_public_id="0",
                ).pack(),
            )
        )

    builder.row(
        InlineKeyboardButton(
            text="К архиву",
            callback_data=OperatorArchiveCallback(
                action="topic_back",
                page=current_page,
                category_id=selected_category_id,
                ticket_public_id="0",
            ).pack(),
        )
    )
    return builder.as_markup()


def build_archived_ticket_markup(
    *,
    ticket_public_id: str,
    page: int,
    category_id: int,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="HTML отчёт",
            callback_data=OperatorActionCallback(
                action="export_html",
                ticket_public_id=ticket_public_id,
            ).pack(),
        ),
        InlineKeyboardButton(
            text="CSV выгрузка",
            callback_data=OperatorActionCallback(
                action="export_csv",
                ticket_public_id=ticket_public_id,
            ).pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="К архиву",
            callback_data=OperatorArchiveCallback(
                action="back",
                page=page,
                category_id=category_id,
                ticket_public_id=ticket_public_id,
            ).pack(),
        )
    )
    return builder.as_markup()


def _build_ticket_button_text(ticket: HistoricalTicketSummary) -> str:
    prefix = ticket.public_number
    if ticket.category_title:
        prefix = f"{prefix} · {shorten_text(ticket.category_title, 12)}"
    return shorten_text(prefix, 32)


def _build_all_topics_button_text(selected_category_id: int) -> str:
    if selected_category_id == ALL_ARCHIVE_CATEGORIES_ID:
        return "• Все темы"
    return "Все темы"


def _build_topic_picker_button_text(
    *,
    category_filter: ArchiveCategoryFilter,
    selected_category_id: int,
) -> str:
    title = shorten_text(category_filter.title, 20)
    if category_filter.id == selected_category_id:
        return f"• {title} · {category_filter.ticket_count}"
    return f"{title} · {category_filter.ticket_count}"
