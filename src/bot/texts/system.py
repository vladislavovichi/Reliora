from __future__ import annotations

from dataclasses import dataclass

from domain.enums.roles import UserRole

PING_RESPONSE_TEXT = "понг"


@dataclass(slots=True, frozen=True)
class CommandHint:
    command: str
    description: str


COMMON_COMMAND_HINTS = (
    CommandHint("/start", "показать приветствие и главное меню"),
    CommandHint("/help", "показать справку по доступным действиям"),
)
OPERATOR_COMMAND_HINTS = (
    CommandHint("/queue", "показать ближайшие заявки в очереди"),
    CommandHint("/take", "взять следующую заявку"),
    CommandHint("/stats", "показать операционную статистику"),
    CommandHint("/ticket <ticket_public_id>", "открыть карточку заявки"),
    CommandHint("/macros [ticket_public_id]", "показать доступные макросы"),
    CommandHint("/tags <ticket_public_id>", "показать теги заявки"),
    CommandHint("/alltags", "показать все доступные теги"),
    CommandHint("/addtag <ticket_public_id> <tag>", "добавить тег к заявке"),
    CommandHint("/rmtag <ticket_public_id> <tag>", "снять тег с заявки"),
    CommandHint("/cancel", "отменить текущее действие оператора"),
)
SUPER_ADMIN_COMMAND_HINTS = (
    CommandHint("/operators", "показать список операторов"),
    CommandHint("/add_operator <telegram_user_id> [display_name]", "выдать права оператора"),
    CommandHint("/remove_operator <telegram_user_id>", "снять права оператора"),
)


def get_start_lines(role: UserRole) -> list[str]:
    if role == UserRole.SUPER_ADMIN:
        return [
            "Здравствуйте. Вы вошли как супер администратор.",
            "Доступны рабочие действия оператора и управление операторами.",
            "Для верхнего уровня используйте меню ниже, "
            "для действий по заявке используйте inline-кнопки под карточкой.",
        ]
    if role == UserRole.OPERATOR:
        return [
            "Здравствуйте. Вы вошли как оператор.",
            "Используйте меню ниже для очереди, статистики и отмены текущего действия.",
            "Для работы с конкретной заявкой используйте inline-кнопки под карточкой.",
        ]
    return [
        "Здравствуйте. Это бот поддержки.",
        "Просто отправьте сообщение одним текстом, "
        "и бот создаст новую заявку или добавит его в уже открытую.",
        "Если нужна подсказка, используйте кнопку «Помощь» или команду /help.",
    ]


def get_help_intro_lines(role: UserRole) -> list[str]:
    if role == UserRole.SUPER_ADMIN:
        return [
            "Справка для супер администратора.",
            "У вас есть все рабочие действия оператора и управление списком операторов.",
        ]
    if role == UserRole.OPERATOR:
        return [
            "Справка для оператора.",
            "Основные действия вынесены в меню, "
            "а действия по заявке доступны через inline-кнопки под карточкой.",
        ]
    return [
        "Справка для пользователя.",
        "Чтобы создать новую заявку или продолжить уже открытую, "
        "просто отправьте сообщение в этот чат.",
    ]


def get_command_hints(role: UserRole) -> tuple[CommandHint, ...]:
    command_hints = [*COMMON_COMMAND_HINTS]
    if role in {UserRole.OPERATOR, UserRole.SUPER_ADMIN}:
        command_hints.extend(OPERATOR_COMMAND_HINTS)
    if role == UserRole.SUPER_ADMIN:
        command_hints.extend(SUPER_ADMIN_COMMAND_HINTS)
    return tuple(command_hints)
