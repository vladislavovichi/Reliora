from __future__ import annotations


def build_ticket_created_text(public_number: str) -> str:
    return (
        f"Заявка {public_number} создана. "
        "Когда оператор подключится, разговор продолжится здесь."
    )


def build_ticket_message_added_text(public_number: str, *, operator_connected: bool) -> str:
    if operator_connected:
        return f"Сообщение по заявке {public_number} передано оператору."
    return (
        f"Сообщение добавлено в заявку {public_number}. "
        "Как только оператор подключится, продолжим здесь."
    )


def build_operator_reply_text(public_number: str, body: str) -> str:
    return f"Ответ по заявке {public_number}\n\n{body}"


def build_ticket_closed_text(public_number: str) -> str:
    return f"Заявка {public_number} закрыта. Если вопрос останется, просто напишите в чат."


def build_finish_ticket_prompt_text(public_number: str) -> str:
    return f"Завершить обращение {public_number}?"


def build_ticket_already_closed_text(public_number: str) -> str:
    return f"Обращение {public_number} уже завершено."


FINISH_TICKET_CANCELLED_TEXT = "Обращение остаётся открытым."
FINISH_TICKET_LOCKED_TEXT = "Обращение сейчас обновляется. Попробуйте ещё раз."
