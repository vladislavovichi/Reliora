from __future__ import annotations

from aiogram.types import CallbackQuery, Message

from application.services.authorization import Permission
from bot.keyboards.reply.main_menu import build_main_menu
from bot.texts.access import get_permission_denied_text
from domain.enums.roles import UserRole


async def deny_event_access(
    event: Message | CallbackQuery,
    *,
    permission: Permission,
    role: UserRole = UserRole.USER,
) -> None:
    message_text = get_permission_denied_text(permission)
    if isinstance(event, CallbackQuery):
        await event.answer(message_text, show_alert=True)
        return

    await event.answer(
        message_text,
        reply_markup=build_main_menu(role),
    )
