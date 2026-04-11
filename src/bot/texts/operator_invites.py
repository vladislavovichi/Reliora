from __future__ import annotations

INVITE_OPERATOR_BUTTON_TEXT = "Пригласить"
INVITE_OPERATOR_STARTED_TEXT = "Приглашение подготовлено."
INVITE_ONBOARDING_NAME_INVALID_TEXT = (
    "Имя не должно быть пустым. Укажите спокойное рабочее имя без лишних деталей."
)
INVITE_ONBOARDING_OPENED_TEXT = "Приглашение распознано."
INVITE_ONBOARDING_CONFIRMED_TEXT = "Роль оператора включена."
INVITE_ONBOARDING_EDIT_TEXT = "Имя можно уточнить."


def build_invite_link_missing_text(code: str) -> str:
    return (
        "Код создан, но публичное имя бота пока недоступно.\n"
        f"Откройте бот и используйте: /start {code}"
    )


def build_invite_invalid_text(error_text: str) -> str:
    return f"Приглашение недоступно.\n{error_text}"


def build_invite_welcome_text(display_name: str) -> str:
    return (
        f"{display_name}, доступ активирован.\n"
        "Рабочее меню уже открыто: здесь доступны очередь, архив, заявки и статистика."
    )
