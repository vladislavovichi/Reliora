from __future__ import annotations

MACRO_NOT_FOUND_TEXT = "Макрос не найден."
MACRO_CREATE_STARTED_TEXT = "Создаём макрос."
MACRO_CREATE_TITLE_PROMPT_TEXT = "Введите название макроса."
MACRO_CREATE_BODY_PROMPT_TEXT = "Теперь отправьте текст макроса."
MACRO_CREATE_EDIT_TEXT = "Можно изменить черновик."
MACRO_CREATE_SAVED_TEXT = "Макрос сохранён."
MACRO_CREATE_CANCELLED_TEXT = "Создание макроса отменено."
MACRO_DRAFT_LOST_TEXT = "Черновик больше не найден. Начните ещё раз."
MACRO_INPUT_COMMAND_BLOCK_TEXT = (
    "Сейчас нужен текст. Отправьте сообщение или нажмите «Отмена»."
)
MACRO_INPUT_NAVIGATION_BLOCK_TEXT = "Сначала завершите текущий шаг или нажмите «Отмена»."
MACRO_TITLE_EDIT_STARTED_TEXT = "Изменяем название."
MACRO_TITLE_EDIT_PROMPT_TEXT = "Отправьте новое название."
MACRO_BODY_EDIT_STARTED_TEXT = "Изменяем текст."
MACRO_BODY_EDIT_PROMPT_TEXT = "Отправьте новый текст."
MACRO_TITLE_UPDATED_TEXT = "Название обновлено."
MACRO_BODY_UPDATED_TEXT = "Текст обновлён."
MACRO_DELETED_TEXT = "Макрос удалён."
MACRO_PREVIEW_READY_TEXT = "Проверьте макрос."
MACRO_PICKER_OPENED_TEXT = "Открыты макросы."
MACRO_PAGE_UPDATED_TEXT = "Список обновлён."
MACRO_PREVIEW_COMMAND_BLOCK_TEXT = "Используйте кнопки ниже."


def build_macro_delete_prompt_text(title: str) -> str:
    return f"Удалить макрос «{title}»?\nЭто действие нельзя отменить."


def build_macro_page_text(page: int) -> str:
    return f"Страница {page}"
