from __future__ import annotations

from aiogram import F, Router
from aiogram.types import Message

router = Router(name="client")


@router.message(F.text & ~F.text.startswith("/"))
async def handle_client_text(message: Message) -> None:
    await message.answer(
        "Your message has been received. Ticket processing will be connected in the next stage."
    )
