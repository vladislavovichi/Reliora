from __future__ import annotations

from collections.abc import Sequence

from aiogram import Bot
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from application.use_cases.tickets.summaries import TicketCategorySummary
from bot.formatters.categories import (
    format_admin_category_details,
    format_admin_category_list,
    paginate_categories,
)
from bot.keyboards.inline.categories import (
    build_admin_category_detail_markup,
    build_admin_category_list_markup,
)


def build_admin_category_list_response(
    *,
    categories: Sequence[TicketCategorySummary],
    page: int,
) -> tuple[str, InlineKeyboardMarkup]:
    page_categories, current_page, total_pages = paginate_categories(categories, page=page)
    return (
        format_admin_category_list(
            page_categories,
            current_page=current_page,
            total_pages=total_pages,
        ),
        build_admin_category_list_markup(
            categories=page_categories,
            current_page=current_page,
            total_pages=total_pages,
        ),
    )


async def edit_admin_category_list(
    *,
    callback: CallbackQuery,
    categories: Sequence[TicketCategorySummary],
    page: int,
    answer_text: str,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer(answer_text)
        return
    text, markup = build_admin_category_list_response(categories=categories, page=page)
    await callback.answer(answer_text)
    await callback.message.edit_text(text, reply_markup=markup)


async def edit_admin_category_details(
    *,
    callback: CallbackQuery,
    category: TicketCategorySummary,
    page: int,
    answer_text: str,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer(answer_text)
        return
    await callback.answer(answer_text)
    await callback.message.edit_text(
        format_admin_category_details(category),
        reply_markup=build_admin_category_detail_markup(category=category, page=page),
    )


async def update_admin_category_source_message(
    *,
    bot: Bot,
    state_data: dict[str, object],
    category: TicketCategorySummary,
    page: int,
    fallback_message: Message,
) -> None:
    chat_id = state_data.get("source_chat_id")
    message_id = state_data.get("source_message_id")
    if isinstance(chat_id, int) and isinstance(message_id, int):
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=format_admin_category_details(category),
            reply_markup=build_admin_category_detail_markup(category=category, page=page),
        )
        return

    await fallback_message.answer(
        format_admin_category_details(category),
        reply_markup=build_admin_category_detail_markup(category=category, page=page),
    )
