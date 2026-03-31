from __future__ import annotations

QUEUE_EMPTY_TEXT = "Очередь пуста."
QUEUE_HEADER_TEXT = "Заявки в очереди:"
NO_QUEUE_TICKETS_TEXT = "Сейчас нет доступных заявок в очереди."
QUEUE_BUSY_TEXT = "Очередь сейчас занята. Попробуйте чуть позже."
OPERATOR_ACTION_IDLE_TEXT = "Сейчас нет активного действия оператора."
OPERATOR_ACTION_CANCELLED_TEXT = "Действие оператора отменено."
MACROS_EMPTY_TEXT = "Макросы пока не настроены."
TAGS_EMPTY_TEXT = "Теги пока не созданы."
OPERATOR_UNKNOWN_TEXT = "Не удалось определить оператора для этого действия."
REPLY_CONTEXT_LOST_TEXT = "Контекст ответа потерян. Запустите действие заново."
REASSIGN_CONTEXT_LOST_TEXT = "Контекст переназначения потерян. Запустите действие заново."
INVALID_REASSIGN_TARGET_TEXT = (
    "Некорректный ввод. Отправьте идентификатор пользователя Telegram, "
    "при необходимости добавьте имя."
)
REPLY_MODE_COMMAND_BLOCK_TEXT = (
    "Сейчас активен режим ответа. Отправьте текст или используйте /cancel."
)
REASSIGN_MODE_COMMAND_BLOCK_TEXT = (
    "Сейчас активен режим переназначения. Отправьте данные оператора\nили используйте /cancel."
)
REASSIGN_TARGET_PROMPT_TEXT = (
    "Отправьте идентификатор пользователя Telegram целевого оператора."
)
APPLY_MACRO_FAILED_TEXT = "Не удалось применить макрос."
OPERATORS_EMPTY_TEXT = "Активный оператор с таким Telegram ID не найден."
OPERATORS_REFRESHED_TEXT = "Список операторов обновлен."
REVOKE_CONFIRM_PROMPT_TEXT = "Подтвердите снятие прав оператора."
REVOKE_CANCELLED_TEXT = "Снятие прав оператора отменено."


def add_operator_guidance() -> str:
    return (
        "Чтобы добавить оператора, используйте команду:\n"
        "/add_operator <telegram_user_id> [display_name]"
    )


def remove_operator_guidance() -> str:
    return "Чтобы снять права оператора, используйте команду:\n/remove_operator <telegram_user_id>"


def invalid_add_operator_usage_text() -> str:
    return "Использование: /add_operator <telegram_user_id> [display_name]"


def invalid_remove_operator_usage_text() -> str:
    return "Использование: /remove_operator <telegram_user_id>"


def invalid_ticket_usage_text() -> str:
    return "Использование: /ticket <ticket_public_id>"


def invalid_macros_usage_text() -> str:
    return "Использование: /macros [ticket_public_id]"


def invalid_tags_usage_text() -> str:
    return "Использование: /tags <ticket_public_id>"


def invalid_add_tag_usage_text() -> str:
    return "Использование: /addtag <ticket_public_id> <tag>"


def invalid_remove_tag_usage_text() -> str:
    return "Использование: /rmtag <ticket_public_id> <tag>"


def build_tag_added_text(ticket_public_number: str, tag: str, tags: str) -> str:
    return f"Тег {tag} добавлен к заявке {ticket_public_number}.\nТекущие теги: {tags}"


def build_tag_already_added_text(ticket_public_number: str, tag: str, tags: str) -> str:
    return f"Тег {tag} уже привязан к заявке {ticket_public_number}.\nТекущие теги: {tags}"


def build_tag_removed_text(ticket_public_number: str, tag: str, tags: str) -> str:
    return f"Тег {tag} снят с заявки {ticket_public_number}.\nТекущие теги: {tags}"


def build_tag_missing_text(ticket_public_number: str, tag: str, tags: str) -> str:
    return f"Тег {tag} не найден у заявки {ticket_public_number}.\nТекущие теги: {tags}"


def build_available_tags_text(tags: list[str] | tuple[str, ...]) -> str:
    return "Доступные теги:\n" + "\n".join(f"- {tag}" for tag in tags)


def build_reply_mode_enabled_text(public_number: str) -> str:
    return (
        f"Отправьте текст ответа для заявки {public_number}.\n"
        "Используйте /cancel, чтобы отменить действие."
    )


def build_reply_mode_callback_text(public_number: str) -> str:
    return f"Режим ответа для заявки {public_number} включен."


def build_reassign_mode_enabled_text() -> str:
    return (
        "Отправьте идентификатор пользователя Telegram целевого оператора, "
        "при необходимости добавьте имя.\n"
        "Пример: 123456789 Иван Иванов\n"
        "Используйте /cancel, чтобы отменить действие."
    )


def build_reassign_mode_callback_text(public_number: str) -> str:
    return f"Режим переназначения для заявки {public_number} включен."


def build_view_opened_text(public_number: str) -> str:
    return f"Открыта заявка {public_number}"


def build_take_answer_text(public_number: str, *, reassigned: bool) -> str:
    if reassigned:
        return f"Заявка {public_number} переназначена."
    return f"Заявка {public_number} назначена."


def build_take_next_fallback_text(public_number: str, status: str) -> str:
    return f"Следующая заявка {public_number} взята в работу. Текущий статус: {status}."


def build_close_text(public_number: str) -> str:
    return f"Заявка {public_number} закрыта."


def build_escalate_text(public_number: str) -> str:
    return f"Заявка {public_number} эскалирована."


def build_reply_sent_text(public_number: str) -> str:
    return f"Ответ по заявке {public_number} отправлен."


def build_reply_delivery_failed_text(public_number: str, error_text: str) -> str:
    return (
        f"Ответ по заявке {public_number} сохранен, "
        f"но доставить его клиенту не удалось: {error_text}"
    )


def build_client_reply_text(public_number: str, body: str) -> str:
    return f"Ответ по заявке {public_number}:\n{body}"


def build_macro_applied_text(title: str) -> str:
    return f"Макрос «{title}» применен."


def build_macro_sent_text(title: str) -> str:
    return f"Макрос «{title}» отправлен."


def build_macro_saved_text(title: str) -> str:
    return f"Макрос «{title}» сохранен."


def build_macro_delivery_failed_text(title: str, error_text: str) -> str:
    return f"Макрос «{title}» сохранен, но доставить его клиенту не удалось: {error_text}"


def build_promote_operator_result_text(
    display_name: str,
    telegram_user_id: int,
    *,
    changed: bool,
) -> str:
    if changed:
        return (
            f"Права оператора выданы пользователю {display_name} "
            f"(Telegram ID: {telegram_user_id})."
        )
    return (
        f"Пользователь {display_name} "
        f"(Telegram ID: {telegram_user_id}) уже является оператором."
    )


def build_revoke_operator_result_text(display_name: str, telegram_user_id: int) -> str:
    return (
        f"Права оператора сняты у пользователя {display_name} "
        f"(Telegram ID: {telegram_user_id})."
    )


def build_revoke_confirm_message(telegram_user_id: int) -> str:
    return (
        "Подтвердите снятие прав оператора "
        f"у пользователя с Telegram ID {telegram_user_id}."
    )
