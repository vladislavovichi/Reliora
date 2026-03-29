from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

router = Router(name="system")


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    await message.answer(
        "Helpdesk bot is online.\n"
        "Send a message to create a ticket placeholder.\n"
        "Use /help to see the currently available commands."
    )


@router.message(Command("help"))
async def handle_help(message: Message) -> None:
    await message.answer(
        "Available commands:\n"
        "/start - show the startup message\n"
        "/help - show this help\n"
        "/ping - health check placeholder\n"
        "/stats - show ticket statistics\n"
        "/queue - show the next queued tickets\n"
        "/take - take the next queued ticket\n"
        "/ticket <ticket_public_id> - inspect ticket details\n"
        "/cancel - cancel the current operator action"
    )


@router.message(Command("ping"))
async def handle_ping(message: Message) -> None:
    await message.answer("pong")
