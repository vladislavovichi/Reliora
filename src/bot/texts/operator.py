from __future__ import annotations

QUEUE_EMPTY_TEXT = "Очередь пока пуста."
QUEUE_HEADER_TEXT = "Очередь"
NO_QUEUE_TICKETS_TEXT = "В очереди сейчас нет заявок."
QUEUE_BUSY_TEXT = "Очередь сейчас занята. Попробуйте ещё раз через пару секунд."
OPERATOR_ACTION_IDLE_TEXT = "Сейчас нечего отменять."
OPERATOR_ACTION_CANCELLED_TEXT = "Действие отменено."
MACROS_EMPTY_TEXT = "Макросов пока нет."
TAGS_EMPTY_TEXT = "Теги пока не добавлены."
OPERATOR_UNKNOWN_TEXT = "Не удалось определить оператора."
REPLY_CONTEXT_LOST_TEXT = "Не удалось продолжить ответ. Откройте заявку ещё раз."
REASSIGN_CONTEXT_LOST_TEXT = "Не удалось продолжить передачу. Откройте заявку ещё раз."
INVALID_REASSIGN_TARGET_TEXT = (
    "Не удалось распознать оператора. Отправьте Telegram ID "
    "и при необходимости добавьте имя."
)
REPLY_MODE_COMMAND_BLOCK_TEXT = (
    "Сейчас открыт режим ответа. Отправьте сообщение или используйте /cancel."
)
REASSIGN_MODE_COMMAND_BLOCK_TEXT = (
    "Сейчас открыт режим передачи. Отправьте Telegram ID\nили используйте /cancel."
)
REASSIGN_TARGET_PROMPT_TEXT = "Укажите Telegram ID оператора."
APPLY_MACRO_FAILED_TEXT = "Не удалось применить макрос."
OPERATORS_EMPTY_TEXT = "Оператор не найден."
OPERATORS_REFRESHED_TEXT = "Список обновлён."
REVOKE_CONFIRM_PROMPT_TEXT = "Подтвердите снятие прав."
REVOKE_CANCELLED_TEXT = "Снятие прав отменено."


def invalid_add_operator_usage_text() -> str:
    return "Формат: /add_operator <telegram_user_id> [display_name]"


def invalid_remove_operator_usage_text() -> str:
    return "Формат: /remove_operator <telegram_user_id>"


def invalid_ticket_usage_text() -> str:
    return "Формат: /ticket <ticket_public_id>"


def invalid_macros_usage_text() -> str:
    return "Формат: /macros [ticket_public_id]"


def invalid_tags_usage_text() -> str:
    return "Формат: /tags <ticket_public_id>"


def invalid_add_tag_usage_text() -> str:
    return "Формат: /addtag <ticket_public_id> <tag>"


def invalid_remove_tag_usage_text() -> str:
    return "Формат: /rmtag <ticket_public_id> <tag>"


def build_tag_added_text(ticket_public_number: str, tag: str, tags: str) -> str:
    return f"Тег «{tag}» добавлен.\nЗаявка: {ticket_public_number}\nСейчас: {tags}"


def build_tag_already_added_text(ticket_public_number: str, tag: str, tags: str) -> str:
    return f"Тег «{tag}» уже есть.\nЗаявка: {ticket_public_number}\nСейчас: {tags}"


def build_tag_removed_text(ticket_public_number: str, tag: str, tags: str) -> str:
    return f"Тег «{tag}» снят.\nЗаявка: {ticket_public_number}\nСейчас: {tags}"


def build_tag_missing_text(ticket_public_number: str, tag: str, tags: str) -> str:
    return f"Тега «{tag}» нет.\nЗаявка: {ticket_public_number}\nСейчас: {tags}"


def build_available_tags_text(tags: list[str] | tuple[str, ...]) -> str:
    return "Доступные теги:\n" + "\n".join(f"- {tag}" for tag in tags)


def build_reply_mode_enabled_text(public_number: str) -> str:
    return (
        f"Отправьте ответ по заявке {public_number}.\n"
        "/cancel — отмена."
    )


def build_reply_mode_callback_text(public_number: str) -> str:
    return f"Можно отвечать по заявке {public_number}."


def build_reassign_mode_enabled_text() -> str:
    return (
        "Отправьте Telegram ID оператора, при необходимости добавьте имя.\n"
        "Пример: 123456789 Иван Иванов\n"
        "/cancel — отмена."
    )


def build_reassign_mode_callback_text(public_number: str) -> str:
    return f"Укажите нового оператора для заявки {public_number}."


def build_view_opened_text(public_number: str) -> str:
    return f"Заявка {public_number} открыта."


def build_take_answer_text(public_number: str, *, reassigned: bool) -> str:
    if reassigned:
        return f"Заявка {public_number} передана другому оператору."
    return f"Заявка {public_number} взята в работу."


def build_take_next_fallback_text(public_number: str, status: str) -> str:
    return f"Заявка {public_number} взята в работу.\nСтатус: {status}."


def build_close_text(public_number: str) -> str:
    return f"Заявка {public_number} закрыта."


def build_close_delivery_failed_text(public_number: str, error_text: str) -> str:
    return (
        f"Заявка {public_number} закрыта, "
        f"но клиент не получил уведомление: {error_text}"
    )


def build_escalate_text(public_number: str) -> str:
    return f"Заявка {public_number} переведена на эскалацию."


def build_reply_sent_text(public_number: str) -> str:
    return f"Ответ по заявке {public_number} отправлен."


def build_reply_delivery_failed_text(public_number: str, error_text: str) -> str:
    return (
        f"Ответ по заявке {public_number} сохранён, "
        f"но клиент его не получил: {error_text}"
    )


def build_forwarded_client_message_text(public_number: str, body: str) -> str:
    return f"Новое сообщение в заявке {public_number}\n\n{body}"


def build_macro_applied_text(title: str) -> str:
    return f"Макрос «{title}» применён."


def build_macro_sent_text(title: str) -> str:
    return f"Макрос «{title}» отправлен."


def build_macro_saved_text(title: str) -> str:
    return f"Макрос «{title}» сохранён."


def build_macro_delivery_failed_text(title: str, error_text: str) -> str:
    return f"Макрос «{title}» сохранён, но клиент его не получил: {error_text}"


def build_promote_operator_result_text(
    display_name: str,
    telegram_user_id: int,
    *,
    changed: bool,
) -> str:
    if changed:
        return f"{display_name} добавлен как оператор. Telegram ID {telegram_user_id}."
    return f"{display_name} уже есть в команде. Telegram ID {telegram_user_id}."


def build_revoke_operator_result_text(display_name: str, telegram_user_id: int) -> str:
    return f"Роль оператора снята: {display_name}, Telegram ID {telegram_user_id}."


def build_revoke_confirm_message(telegram_user_id: int) -> str:
    return f"Снять роль оператора у пользователя с Telegram ID {telegram_user_id}?"


def build_queue_page_callback_text(page: int) -> str:
    return f"Страница {page}"
