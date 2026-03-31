from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from bot.presentation import HELP_BUTTON_TEXT, build_help_text, build_main_menu, build_start_text
from domain.enums.roles import UserRole

router = Router(name="system")


@router.message(CommandStart())
async def handle_start(
    message: Message,
    event_user_role: UserRole = UserRole.USER,
) -> None:
    await _send_start_message(message, role=event_user_role)


@router.message(Command("help"))
async def handle_help_with_role(
    message: Message,
    event_user_role: UserRole = UserRole.USER,
) -> None:
    await _send_help_message(message, role=event_user_role)


@router.message(F.text == HELP_BUTTON_TEXT)
async def handle_help_button(
    message: Message,
    event_user_role: UserRole = UserRole.USER,
) -> None:
    await _send_help_message(message, role=event_user_role)


@router.message(Command("ping"))
async def handle_ping(message: Message) -> None:
    await message.answer("понг")


async def _send_start_message(message: Message, *, role: UserRole) -> None:
    await message.answer(
        build_start_text(role),
        reply_markup=build_main_menu(role),
    )


async def _send_help_message(message: Message, *, role: UserRole) -> None:
    await message.answer(
        build_help_text(role),
        reply_markup=build_main_menu(role),
    )
