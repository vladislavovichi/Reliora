from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

router = Router(name="system")


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    await message.answer(
        "Helpdesk bootstrap is online. Ticket workflows will be added in later iterations."
    )


@router.message(Command("help"))
async def handle_help(message: Message) -> None:
    await message.answer(
        "This bot currently exposes infrastructure-only bootstrap handlers. "
        "Business commands are not implemented yet."
    )
