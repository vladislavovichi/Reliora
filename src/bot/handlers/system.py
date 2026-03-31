from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from domain.enums.roles import UserRole

router = Router(name="system")


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    await message.answer(
        "Бот поддержки запущен.\n"
        "Отправьте сообщение, чтобы создать новую заявку.\n"
        "Используйте /help, чтобы посмотреть доступные команды."
    )


@router.message(Command("help"))
async def handle_help_with_role(
    message: Message,
    event_user_role: UserRole = UserRole.USER,
) -> None:
    await message.answer(_build_help_text(event_user_role))


@router.message(Command("ping"))
async def handle_ping(message: Message) -> None:
    await message.answer("понг")


def _build_help_text(role: UserRole) -> str:
    lines = [
        "Доступные команды:",
        "/start - показать стартовое сообщение",
        "/help - показать эту справку",
        "/ping - проверить доступность бота",
    ]

    if role in {UserRole.OPERATOR, UserRole.SUPER_ADMIN}:
        lines.extend(
            [
                "/stats - показать статистику по заявкам",
                "/queue - показать ближайшие заявки в очереди",
                "/take - взять следующую заявку из очереди",
                "/ticket <ticket_public_id> - показать детали заявки",
                "/macros [ticket_public_id] - показать доступные макросы",
                "/tags <ticket_public_id> - показать теги заявки",
                "/alltags - показать все доступные теги",
                "/addtag <ticket_public_id> <tag> - добавить тег к заявке",
                "/rmtag <ticket_public_id> <tag> - снять тег с заявки",
                "/cancel - отменить текущее действие оператора",
            ]
        )

    if role == UserRole.SUPER_ADMIN:
        lines.append("Команды управления операторами будут доступны после следующего этапа.")

    return "\n".join(lines)
