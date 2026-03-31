from __future__ import annotations

from dataclasses import dataclass

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from domain.enums.roles import UserRole

HELP_BUTTON_TEXT = "Помощь"
QUEUE_BUTTON_TEXT = "Очередь"
TAKE_NEXT_BUTTON_TEXT = "Взять следующий"
STATS_BUTTON_TEXT = "Статистика"
CANCEL_BUTTON_TEXT = "Отмена"
OPERATORS_BUTTON_TEXT = "Операторы"
ADD_OPERATOR_BUTTON_TEXT = "Добавить оператора"
REMOVE_OPERATOR_BUTTON_TEXT = "Удалить оператора"

USER_NAVIGATION_BUTTONS = frozenset({HELP_BUTTON_TEXT})
OPERATOR_NAVIGATION_BUTTONS = frozenset(
    {
        QUEUE_BUTTON_TEXT,
        TAKE_NEXT_BUTTON_TEXT,
        STATS_BUTTON_TEXT,
        CANCEL_BUTTON_TEXT,
    }
)
SUPER_ADMIN_NAVIGATION_BUTTONS = frozenset(
    {
        OPERATORS_BUTTON_TEXT,
        ADD_OPERATOR_BUTTON_TEXT,
        REMOVE_OPERATOR_BUTTON_TEXT,
    }
)


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
    CommandHint(
        "/add_operator <telegram_user_id> [display_name]",
        "выдать права оператора",
    ),
    CommandHint(
        "/remove_operator <telegram_user_id>",
        "снять права оператора",
    ),
)


def build_start_text(role: UserRole) -> str:
    if role == UserRole.SUPER_ADMIN:
        lines = [
            "Здравствуйте. Вы вошли как супер администратор.",
            "Доступны рабочие действия оператора и управление операторами.",
            "Для верхнего уровня используйте меню ниже, для действий по заявке"
            " используйте inline-кнопки под карточкой.",
        ]
    elif role == UserRole.OPERATOR:
        lines = [
            "Здравствуйте. Вы вошли как оператор.",
            "Используйте меню ниже для очереди, статистики и отмены текущего действия.",
            "Для работы с конкретной заявкой используйте inline-кнопки под карточкой.",
        ]
    else:
        lines = [
            "Здравствуйте. Это бот поддержки.",
            "Просто отправьте сообщение одним текстом, и бот создаст новую заявку"
            " или добавит его в уже открытую.",
            "Если нужна подсказка, используйте кнопку «Помощь» или команду /help.",
        ]

    return "\n".join(lines)


def build_help_text(role: UserRole) -> str:
    lines = [*_build_help_intro(role), "", "Команды:"]
    lines.extend(
        f"{command_hint.command} - {command_hint.description}"
        for command_hint in _build_command_hints(role)
    )

    navigation_lines = _build_navigation_help(role)
    if navigation_lines:
        lines.extend(["", "Кнопки меню:", *navigation_lines])

    return "\n".join(lines)


def build_main_menu(role: UserRole) -> ReplyKeyboardMarkup:
    keyboard_rows: list[list[KeyboardButton]] = []

    if role == UserRole.USER:
        keyboard_rows.append([KeyboardButton(text=HELP_BUTTON_TEXT)])
        placeholder = "Опишите проблему одним сообщением"
    else:
        keyboard_rows.extend(
            [
                [
                    KeyboardButton(text=QUEUE_BUTTON_TEXT),
                    KeyboardButton(text=TAKE_NEXT_BUTTON_TEXT),
                ],
                [
                    KeyboardButton(text=STATS_BUTTON_TEXT),
                    KeyboardButton(text=CANCEL_BUTTON_TEXT),
                ],
            ]
        )
        placeholder = "Выберите действие"

        if role == UserRole.SUPER_ADMIN:
            keyboard_rows.extend(
                [
                    [KeyboardButton(text=OPERATORS_BUTTON_TEXT)],
                    [
                        KeyboardButton(text=ADD_OPERATOR_BUTTON_TEXT),
                        KeyboardButton(text=REMOVE_OPERATOR_BUTTON_TEXT),
                    ],
                ]
            )

        keyboard_rows.append([KeyboardButton(text=HELP_BUTTON_TEXT)])

    return ReplyKeyboardMarkup(
        keyboard=keyboard_rows,
        resize_keyboard=True,
        input_field_placeholder=placeholder,
    )


def build_add_operator_guidance() -> str:
    return (
        "Чтобы добавить оператора, используйте команду:\n"
        "/add_operator <telegram_user_id> [display_name]"
    )


def build_remove_operator_guidance() -> str:
    return (
        "Чтобы снять права оператора, используйте команду:\n"
        "/remove_operator <telegram_user_id>"
    )


def _build_help_intro(role: UserRole) -> list[str]:
    if role == UserRole.SUPER_ADMIN:
        return [
            "Справка для супер администратора.",
            "У вас есть все рабочие действия оператора и управление списком операторов.",
        ]

    if role == UserRole.OPERATOR:
        return [
            "Справка для оператора.",
            "Основные действия вынесены в меню, а действия по заявке доступны"
            " через inline-кнопки под карточкой.",
        ]

    return [
        "Справка для пользователя.",
        "Чтобы создать новую заявку или продолжить уже открытую, просто отправьте сообщение"
        " в этот чат.",
    ]


def _build_command_hints(role: UserRole) -> tuple[CommandHint, ...]:
    command_hints = [*COMMON_COMMAND_HINTS]

    if role in {UserRole.OPERATOR, UserRole.SUPER_ADMIN}:
        command_hints.extend(OPERATOR_COMMAND_HINTS)

    if role == UserRole.SUPER_ADMIN:
        command_hints.extend(SUPER_ADMIN_COMMAND_HINTS)

    return tuple(command_hints)


def _build_navigation_help(role: UserRole) -> list[str]:
    if role == UserRole.SUPER_ADMIN:
        return [
            f"«{QUEUE_BUTTON_TEXT}» - открыть очередь заявок",
            f"«{TAKE_NEXT_BUTTON_TEXT}» - взять следующую заявку в работу",
            f"«{STATS_BUTTON_TEXT}» - посмотреть статистику",
            f"«{CANCEL_BUTTON_TEXT}» - отменить текущее действие",
            f"«{OPERATORS_BUTTON_TEXT}» - открыть список операторов",
            f"«{ADD_OPERATOR_BUTTON_TEXT}» - показать подсказку по выдаче прав",
            f"«{REMOVE_OPERATOR_BUTTON_TEXT}» - показать подсказку по отзыву прав",
            f"«{HELP_BUTTON_TEXT}» - повторно открыть справку",
        ]

    if role == UserRole.OPERATOR:
        return [
            f"«{QUEUE_BUTTON_TEXT}» - открыть очередь заявок",
            f"«{TAKE_NEXT_BUTTON_TEXT}» - взять следующую заявку в работу",
            f"«{STATS_BUTTON_TEXT}» - посмотреть статистику",
            f"«{CANCEL_BUTTON_TEXT}» - отменить текущее действие",
            f"«{HELP_BUTTON_TEXT}» - повторно открыть справку",
        ]

    return [f"«{HELP_BUTTON_TEXT}» - показать краткую справку"]
