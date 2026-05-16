from __future__ import annotations

from datetime import datetime
from typing import Any

from application.ai.summaries import TicketAssistSnapshot
from application.use_cases.tickets.summaries import TicketDetailsSummary
from domain.enums.tickets import TicketMessageSenderType
from mini_app.serializers.common import serialize_datetime


def serialize_ticket_timeline(
    ticket: TicketDetailsSummary | None,
    ai_snapshot: TicketAssistSnapshot | None = None,
) -> dict[str, Any]:
    if ticket is None:
        return {"items": [], "warning": "Ticket history is temporarily unavailable."}

    items: list[dict[str, Any]] = [_serialize_ticket_created(ticket)]

    if ticket.assigned_operator_name:
        items.append(_serialize_current_assignment(ticket))

    for index, message in enumerate(ticket.message_history, start=1):
        items.append(_serialize_message(index=index, message=message))

    for note in ticket.internal_notes:
        items.append(_serialize_note(note))

    if ai_snapshot is not None and ai_snapshot.summary_generated_at is not None:
        items.append(_serialize_ai_summary(ai_snapshot))

    if ticket.closed_at is not None:
        items.append(_serialize_ticket_closed(ticket))

    return {
        "items": sorted(items, key=lambda item: (item["created_at"] or "", item["id"])),
        "warning": None,
    }


def _serialize_ticket_created(ticket: TicketDetailsSummary) -> dict[str, Any]:
    return _build_timeline_item(
        item_id="ticket-created",
        item_type="ticket_created",
        title="Ticket created",
        description=f"{ticket.public_number} was opened.",
        actor_label="Customer",
        created_at=ticket.created_at,
        metadata={
            "status": _normalize_status(ticket.status),
            "priority": ticket.priority,
            "category": _normalize_optional_text(ticket.category_title),
        },
    )


def _serialize_current_assignment(ticket: TicketDetailsSummary) -> dict[str, Any]:
    return _build_timeline_item(
        item_id="ticket-current-assignment",
        item_type="ticket_assigned",
        title="Current assignment",
        description=f"Ticket is assigned to {ticket.assigned_operator_name}.",
        actor_label=ticket.assigned_operator_name,
        created_at=ticket.updated_at,
        metadata={"derived": True},
    )


def _serialize_message(*, index: int, message: Any) -> dict[str, Any]:
    is_operator = message.sender_type == TicketMessageSenderType.OPERATOR
    has_attachment = message.attachment is not None
    text = _clip_timeline_text(message.text)
    if text is None and has_attachment:
        text = "Attachment added."
    return _build_timeline_item(
        item_id=f"message-{index}",
        item_type="operator_reply" if is_operator else "message_received",
        title="Operator replied" if is_operator else "Customer message received",
        description=text or "Message without text.",
        actor_label=_normalize_message_actor(message),
        created_at=message.created_at,
        metadata=_serialize_attachment_metadata(message.attachment),
    )


def _serialize_note(note: Any) -> dict[str, Any]:
    return _build_timeline_item(
        item_id=f"note-{note.id}",
        item_type="internal_note_added",
        title="Internal note added",
        description=_clip_timeline_text(note.text) or "Internal note added.",
        actor_label=_normalize_actor_label(note.author_operator_name),
        created_at=note.created_at,
        metadata=None,
    )


def _serialize_ai_summary(ai_snapshot: TicketAssistSnapshot) -> dict[str, Any]:
    return _build_timeline_item(
        item_id="ai-summary-generated",
        item_type="ai_summary_generated",
        title="AI summary generated",
        description=ai_snapshot.status_note or "AI assistance summary was generated.",
        actor_label="AI assistant",
        created_at=ai_snapshot.summary_generated_at,
        metadata={
            "summary_status": ai_snapshot.summary_status.value,
            "model_id": ai_snapshot.model_id,
        },
    )


def _serialize_ticket_closed(ticket: TicketDetailsSummary) -> dict[str, Any]:
    return _build_timeline_item(
        item_id="ticket-closed",
        item_type="ticket_closed",
        title="Ticket closed",
        description=f"{ticket.public_number} was closed.",
        actor_label=_normalize_actor_label(ticket.assigned_operator_name),
        created_at=ticket.closed_at,
        metadata={"status": "closed"},
    )


def _build_timeline_item(
    *,
    item_id: str,
    item_type: str,
    title: str,
    description: str,
    actor_label: str | None,
    created_at: datetime | None,
    metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "id": item_id,
        "type": item_type,
        "title": title,
        "description": description,
        "actor_label": actor_label,
        "created_at": serialize_datetime(created_at),
        "metadata": _sanitize_timeline_metadata(metadata),
    }


def _clip_timeline_text(value: str | None, *, limit: int = 180) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.split())
    if not normalized:
        return None
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 1].rstrip()}…"


def _sanitize_timeline_metadata(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    if not metadata:
        return None
    safe = {
        key: value
        for key, value in metadata.items()
        if value is not None and isinstance(value, str | int | float | bool)
    }
    return safe or None


def _serialize_attachment_metadata(attachment: Any | None) -> dict[str, Any] | None:
    if attachment is None:
        return None
    return {
        "attachment_kind": attachment.kind.value,
        "attachment_filename": attachment.filename,
    }


def _normalize_message_actor(message: Any) -> str:
    is_operator = message.sender_type == TicketMessageSenderType.OPERATOR
    if is_operator and message.sender_operator_name:
        return str(message.sender_operator_name)
    return "Operator" if is_operator else "Customer"


def _normalize_actor_label(value: str | None) -> str:
    return value or "Operator"


def _normalize_status(value: Any) -> str:
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None
