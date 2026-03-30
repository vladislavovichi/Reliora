from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

router = Router(name="system")


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    await message.answer(
        "Бот поддержки запущен.\n"
        "Отправьте сообщение, чтобы создать новую заявку.\n"
        "Используйте /help, чтобы посмотреть доступные команды."
    )


@router.message(Command("help"))
async def handle_help(message: Message) -> None:
    await message.answer(
        "Доступные команды:\n"
        "/start - показать стартовое сообщение\n"
        "/help - показать эту справку\n"
        "/ping - проверить доступность бота\n"
        "/stats - показать статистику по заявкам\n"
        "/queue - показать ближайшие заявки в очереди\n"
        "/take - взять следующую заявку из очереди\n"
        "/ticket <ticket_public_id> - показать детали заявки\n"
        "/macros [ticket_public_id] - показать доступные макросы\n"
        "/tags <ticket_public_id> - показать теги заявки\n"
        "/alltags - показать все доступные теги\n"
        "/addtag <ticket_public_id> <tag> - добавить тег к заявке\n"
        "/rmtag <ticket_public_id> <tag> - снять тег с заявки\n"
        "/cancel - отменить текущее действие оператора"
    )


@router.message(Command("ping"))
async def handle_ping(message: Message) -> None:
    await message.answer("понг")
