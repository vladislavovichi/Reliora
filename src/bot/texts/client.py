from __future__ import annotations


def build_ticket_created_text(public_number: str) -> str:
    return (
        f"Заявка {public_number} создана и поставлена в очередь. "
        "Оператор скоро ее возьмет в работу."
    )


def build_ticket_message_added_text(public_number: str) -> str:
    return f"Ваше сообщение добавлено в заявку {public_number}. Работа по ней продолжается."
