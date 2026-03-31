from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from bot.formatters.system import build_help_text, build_start_text
from bot.keyboards.reply.main_menu import build_main_menu
from bot.texts.buttons import HELP_BUTTON_TEXT
from bot.texts.system import PING_RESPONSE_TEXT
from domain.enums.roles import UserRole

router = Router(name="system")


@router.message(CommandStart())
async def handle_start(
    message: Message,
    event_user_role: UserRole = UserRole.USER,
) -> None:
    await message.answer(
        build_start_text(event_user_role),
        reply_markup=build_main_menu(event_user_role),
    )


@router.message(Command("help"))
@router.message(F.text == HELP_BUTTON_TEXT)
async def handle_help(
    message: Message,
    event_user_role: UserRole = UserRole.USER,
) -> None:
    await message.answer(
        build_help_text(event_user_role),
        reply_markup=build_main_menu(event_user_role),
    )


@router.message(Command("ping"))
async def handle_ping(message: Message) -> None:
    await message.answer(PING_RESPONSE_TEXT)
