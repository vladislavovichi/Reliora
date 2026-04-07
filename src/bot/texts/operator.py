from __future__ import annotations

QUEUE_EMPTY_TEXT = "Очередь пока пуста."
QUEUE_HEADER_TEXT = "Очередь"
NO_QUEUE_TICKETS_TEXT = "Сейчас новых заявок нет."
MY_TICKETS_EMPTY_TEXT = "У вас пока нет активных заявок."
QUEUE_BUSY_TEXT = "Очередь сейчас занята. Попробуйте ещё раз через пару секунд."
OPERATOR_ACTION_IDLE_TEXT = "Сейчас нечего отменять."
OPERATOR_ACTION_CANCELLED_TEXT = "Действие отменено."
MACROS_EMPTY_TEXT = "Макросов пока нет."
TAGS_EMPTY_TEXT = "Метки пока не настроены."
TAG_ACTION_STALE_TEXT = "Экран меток устарел. Откройте заявку ещё раз."
OPERATOR_UNKNOWN_TEXT = "Не удалось определить оператора."
REPLY_CONTEXT_LOST_TEXT = "Не удалось продолжить ответ. Откройте заявку ещё раз."
REASSIGN_CONTEXT_LOST_TEXT = "Не удалось продолжить передачу. Откройте заявку ещё раз."
ACTIVE_TICKET_REQUIRED_TEXT = "Откройте диалог из «Мои заявки» или возьмите новую заявку."
ACTIVE_TICKET_UNAVAILABLE_TEXT = "Текущий диалог больше недоступен. Откройте другую заявку."
INVALID_REASSIGN_TARGET_TEXT = (
    "Не удалось распознать оператора. Отправьте Telegram ID и при необходимости добавьте имя."
)
REPLY_MODE_COMMAND_BLOCK_TEXT = (
    "Сейчас открыт ответ по заявке. Отправьте сообщение или нажмите «Отмена»."
)
REASSIGN_MODE_COMMAND_BLOCK_TEXT = (
    "Сейчас открыт шаг передачи. Отправьте Telegram ID нового оператора или нажмите «Отмена»."
)
REASSIGN_TARGET_PROMPT_TEXT = "Укажите Telegram ID нового оператора."
APPLY_MACRO_FAILED_TEXT = "Не удалось применить макрос."
OPERATORS_EMPTY_TEXT = "Оператор не найден."
OPERATORS_REFRESHED_TEXT = "Список обновлён."
REVOKE_CONFIRM_PROMPT_TEXT = "Подтвердите снятие роли."
REVOKE_CANCELLED_TEXT = "Снятие роли отменено."
OPERATOR_ADD_STARTED_TEXT = "Добавляем оператора."
OPERATOR_ADD_PROMPT_TEXT = (
    "Отправьте Telegram ID и, если нужно, имя одной строкой.\n"
    "Например: 123456789 Анна Смирнова"
)
OPERATOR_ADD_INVALID_TEXT = (
    "Не удалось распознать данные. "
    "Укажите Telegram ID и при необходимости имя."
)
OPERATOR_INPUT_NAVIGATION_BLOCK_TEXT = (
    "Сначала завершите текущий шаг или нажмите «Отмена»."
)
TAGS_UPDATED_TEXT = "Метки обновлены."


def build_tag_added_text(ticket_public_number: str, tag: str, tags: str) -> str:
    return f"Метка «{tag}» добавлена.\nЗаявка: {ticket_public_number}\nСейчас: {tags}"


def build_tag_already_added_text(ticket_public_number: str, tag: str, tags: str) -> str:
    return f"Метка «{tag}» уже есть.\nЗаявка: {ticket_public_number}\nСейчас: {tags}"


def build_tag_removed_text(ticket_public_number: str, tag: str, tags: str) -> str:
    return f"Метка «{tag}» снята.\nЗаявка: {ticket_public_number}\nСейчас: {tags}"


def build_tag_missing_text(ticket_public_number: str, tag: str, tags: str) -> str:
    return f"Метки «{tag}» нет.\nЗаявка: {ticket_public_number}\nСейчас: {tags}"


def build_reply_mode_enabled_text(public_number: str) -> str:
    return (
        f"Отправьте ответ по заявке {public_number}.\n"
        "Если передумали, нажмите «Отмена»."
    )


def build_reply_mode_callback_text(public_number: str) -> str:
    return f"Текущий диалог — {public_number}."


def build_active_ticket_opened_text(public_number: str) -> str:
    return f"Текущий диалог — {public_number}."


def build_reassign_mode_enabled_text() -> str:
    return (
        "Отправьте Telegram ID нового оператора, при необходимости добавьте имя.\n"
        "Например: 123456789 Иван Иванов"
    )


def build_reassign_mode_callback_text(public_number: str) -> str:
    return f"Укажите нового оператора для заявки {public_number}."


def build_view_opened_text(public_number: str) -> str:
    return f"Заявка {public_number} открыта."


def build_more_actions_opened_text(public_number: str) -> str:
    return f"Ещё по заявке {public_number}."


def build_take_answer_text(public_number: str, *, reassigned: bool) -> str:
    if reassigned:
        return f"Заявка {public_number} передана другому оператору."
    return f"Заявка {public_number} взята в работу."


def build_take_next_fallback_text(public_number: str, status: str) -> str:
    return f"Заявка {public_number} взята в работу.\nСтатус: {status}."


def build_close_text(public_number: str) -> str:
    return f"Заявка {public_number} закрыта.\nДиалог завершён."


def build_close_delivery_failed_text(public_number: str, error_text: str) -> str:
    return (
        f"Заявка {public_number} закрыта. Диалог завершён, "
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
    return f"Другая заявка · {public_number}\nТекущий диалог не менялся.\n\n{body}"


def build_active_client_message_text(public_number: str, body: str) -> str:
    return f"Текущий диалог · {public_number}\nКлиент\n\n{body}"


def build_macro_applied_text(title: str) -> str:
    return f"Макрос «{title}» применён."


def build_macro_sent_text(title: str) -> str:
    return f"Макрос «{title}» отправлен."


def build_macro_saved_text(title: str) -> str:
    return f"Макрос «{title}» сохранён."


def build_macro_delivery_failed_text(title: str, error_text: str) -> str:
    return f"Макрос «{title}» сохранён, но клиент его не получил: {error_text}"


def build_client_finished_ticket_text(public_number: str) -> str:
    return f"Клиент завершил обращение {public_number}."


def build_promote_operator_result_text(
    display_name: str,
    telegram_user_id: int,
    *,
    changed: bool,
) -> str:
    if changed:
        return f"{display_name} добавлен в команду. Telegram ID {telegram_user_id}."
    return f"{display_name} уже есть в команде. Telegram ID {telegram_user_id}."


def build_revoke_operator_result_text(display_name: str, telegram_user_id: int) -> str:
    return f"Роль оператора снята: {display_name}, Telegram ID {telegram_user_id}."


def build_revoke_confirm_message(telegram_user_id: int) -> str:
    return f"Снять роль оператора у пользователя с Telegram ID {telegram_user_id}?"


def build_queue_page_callback_text(page: int) -> str:
    return f"Страница {page}"
