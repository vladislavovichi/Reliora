from __future__ import annotations


def build_ticket_closed_with_feedback_text(public_number: str) -> str:
    return (
        f"Обращение {public_number} закрыто. Если что-то ещё понадобится, просто напишите сюда."
        "\n\nЕсли захотите, оцените, как всё прошло."
    )


TICKET_FEEDBACK_ALREADY_SAVED_TEXT = "Оценка уже сохранена."
TICKET_FEEDBACK_COMMENT_ALREADY_SAVED_TEXT = "Комментарий уже сохранён."
TICKET_FEEDBACK_COMMENT_EMPTY_TEXT = "Можно отправить пару слов одним сообщением."
TICKET_FEEDBACK_NOT_AVAILABLE_TEXT = "Оценка доступна после закрытия обращения."
TICKET_FEEDBACK_STALE_TEXT = "Эта кнопка уже неактуальна."
TICKET_FEEDBACK_THANK_YOU_TEXT = (
    "Спасибо. Если захотите, можно оставить короткий комментарий."
)
TICKET_FEEDBACK_COMMENT_PROMPT_TEXT = "Напишите пару слов одним сообщением, если удобно."
TICKET_FEEDBACK_COMMENT_SAVED_TEXT = "Спасибо. Всё сохранили."
TICKET_FEEDBACK_SKIPPED_TEXT = "Спасибо за оценку."
