from __future__ import annotations

from application.use_cases.tickets.summaries import TicketAttachmentSummary
from bot.formatters.ticket_messages import format_attachment_label


def build_client_delivery_body(
    *,
    public_number: str,
    text: str | None,
    attachment: TicketAttachmentSummary | None,
) -> str:
    return _build_delivery_body(
        header=f"Ответ по заявке {public_number}",
        actor_label=None,
        text=text,
        attachment=attachment,
    )


def build_operator_delivery_body(
    *,
    public_number: str,
    text: str | None,
    attachment: TicketAttachmentSummary | None,
    active_context: bool,
) -> str:
    if active_context:
        parts = [f"Текущий диалог · {public_number}\nКлиент"]
        if attachment is not None:
            parts.append(format_attachment_label(attachment))
        if text:
            parts.append(text)
        return "\n\n".join(parts)
    return _build_delivery_body(
        header=f"Другая заявка · {public_number}\nТекущий диалог не менялся.",
        actor_label=None,
        text=text,
        attachment=attachment,
    )


def _build_delivery_body(
    *,
    header: str,
    actor_label: str | None,
    text: str | None,
    attachment: TicketAttachmentSummary | None,
    context_line: str | None = None,
) -> str:
    parts = [header]
    if context_line is not None:
        parts.append(context_line)
    if actor_label is not None:
        parts.append(actor_label)
    if attachment is not None:
        parts.append(format_attachment_label(attachment))
    if text:
        parts.append(text)
    return "\n\n".join(parts)
