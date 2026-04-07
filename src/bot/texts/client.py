from __future__ import annotations


def build_ticket_created_text(public_number: str) -> str:
    return (
        f"Заявка {public_number} создана. "
        "Когда оператор подключится, разговор продолжится здесь."
    )


def build_ticket_message_added_text(public_number: str) -> str:
    return f"Сообщение добавлено в заявку {public_number}."


def build_operator_reply_text(public_number: str, body: str) -> str:
    return f"Ответ по заявке {public_number}\n\n{body}"


def build_ticket_closed_text(public_number: str) -> str:
    return f"Заявка {public_number} закрыта. Если вопрос останется, просто напишите в чат."
