from __future__ import annotations

INTAKE_CATEGORY_PROMPT_TEXT = "Выберите тему обращения. Дальше продолжим без лишних шагов."
INTAKE_CATEGORY_STALE_TEXT = "Этот выбор уже неактуален. Если нужно, просто начните заново."
INTAKE_CANCELLED_TEXT = "Новое обращение отменено. Когда будете готовы, просто напишите в чат."

CATEGORY_CREATE_STARTED_TEXT = "Новая тема."
CATEGORY_CREATE_SAVED_TEXT = "Тема сохранена."
CATEGORY_EDIT_STARTED_TEXT = "Изменение темы."
CATEGORY_LIST_UPDATED_TEXT = "Список тем обновлён."
CATEGORY_NOT_FOUND_TEXT = "Тема не найдена."
CATEGORY_TITLE_UPDATED_TEXT = "Название обновлено."
CATEGORY_ENABLED_TEXT = "Тема снова доступна в новом обращении."
CATEGORY_DISABLED_TEXT = "Тема скрыта из нового обращения."
CATEGORY_DRAFT_LOST_TEXT = "Черновик темы потерян. Начните заново."
CATEGORY_CREATE_TITLE_PROMPT_TEXT = "Отправьте название темы."
CATEGORY_EDIT_TITLE_PROMPT_TEXT = "Отправьте новое название темы."
CATEGORY_INPUT_NAVIGATION_BLOCK_TEXT = (
    "Сейчас ожидается название темы. Завершите шаг или нажмите «Отмена»."
)
CATEGORY_INPUT_COMMAND_BLOCK_TEXT = "Сначала завершите текущий шаг."


def build_intake_message_prompt_text(category_title: str) -> str:
    return "\n".join(
        [
            "Тема",
            category_title,
            "",
            "Опишите ситуацию одним сообщением.",
        ]
    )


def build_intake_category_selected_text(category_title: str) -> str:
    return "\n".join(
        [
            "Тема",
            category_title,
            "",
            "Сохранил. Формирую обращение.",
        ]
    )


def build_intake_attachment_prompt_text(category_title: str) -> str:
    return "\n".join(
        [
            "Тема",
            category_title,
            "",
            "Вложение уже сохранено. Добавьте короткое описание одним сообщением.",
        ]
    )
