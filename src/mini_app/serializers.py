from __future__ import annotations

from datetime import datetime
from typing import Any

from application.ai.summaries import TicketAssistSnapshot, TicketReplyDraft
from application.services.stats import HelpdeskAnalyticsSnapshot
from application.use_cases.ai.settings import RuntimeAISettings
from application.use_cases.tickets.operator_invites import OperatorInviteCodeSummary
from application.use_cases.tickets.summaries import (
    AccessContextSummary,
    HistoricalTicketSummary,
    MacroSummary,
    OperatorSummary,
    OperatorTicketSummary,
    QueuedTicketSummary,
    TicketAttachmentSummary,
    TicketDetailsSummary,
)
from domain.enums.tickets import TicketMessageSenderType, TicketSentiment


def serialize_access_context(access_context: AccessContextSummary) -> dict[str, Any]:
    return {
        "telegram_user_id": access_context.telegram_user_id,
        "role": access_context.role.value,
    }


def serialize_ai_settings(settings: RuntimeAISettings) -> dict[str, Any]:
    return {
        "ai_summaries_enabled": settings.ai_summaries_enabled,
        "ai_macro_suggestions_enabled": settings.ai_macro_suggestions_enabled,
        "ai_reply_drafts_enabled": settings.ai_reply_drafts_enabled,
        "ai_category_prediction_enabled": settings.ai_category_prediction_enabled,
        "default_model_id": settings.default_model_id,
        "max_history_messages": settings.max_history_messages,
        "reply_draft_tone": settings.reply_draft_tone,
        "operator_must_review_ai": settings.operator_must_review_ai,
    }


def serialize_queue_ticket(ticket: QueuedTicketSummary) -> dict[str, Any]:
    return {
        "public_id": str(ticket.public_id),
        "public_number": ticket.public_number,
        "subject": ticket.subject,
        "priority": ticket.priority,
        "status": ticket.status.value,
        "category_title": ticket.category_title,
    }


def serialize_operator_ticket(ticket: OperatorTicketSummary) -> dict[str, Any]:
    return {
        "public_id": str(ticket.public_id),
        "public_number": ticket.public_number,
        "subject": ticket.subject,
        "priority": ticket.priority,
        "status": ticket.status.value,
        "category_title": ticket.category_title,
    }


def serialize_dashboard_ticket_preview(
    ticket: TicketDetailsSummary | QueuedTicketSummary | OperatorTicketSummary,
) -> dict[str, Any]:
    return {
        "public_id": str(ticket.public_id),
        "public_number": ticket.public_number,
        "subject": ticket.subject,
        "status": ticket.status.value,
        "priority": getattr(ticket, "priority", None),
        "category": getattr(ticket, "category_title", None),
        "category_title": getattr(ticket, "category_title", None),
        "assigned_operator": _serialize_assigned_operator(ticket),
        "last_activity_at": _serialize_datetime(_resolve_ticket_last_activity(ticket)),
        "sla_state": _serialize_sla_state(ticket),
        "sentiment": _serialize_ticket_sentiment(ticket),
        "last_message_sender_type": (
            ticket.last_message_sender_type.value
            if isinstance(ticket, TicketDetailsSummary) and ticket.last_message_sender_type
            else None
        ),
    }


def serialize_dashboard_bucket(
    *,
    key: str,
    label: str,
    tickets: list[TicketDetailsSummary | QueuedTicketSummary | OperatorTicketSummary],
    route: str,
    severity: str = "neutral",
    empty_label: str = "Сейчас пусто.",
    unavailable_reason: str | None = None,
    preview_limit: int = 5,
) -> dict[str, Any]:
    sorted_tickets = sorted(tickets, key=_ticket_activity_sort_value, reverse=True)
    return {
        "key": key,
        "label": label,
        "count": len(tickets),
        "tickets": [
            serialize_dashboard_ticket_preview(ticket) for ticket in sorted_tickets[:preview_limit]
        ],
        "route": route,
        "severity": severity,
        "empty_label": empty_label,
        "unavailable_reason": unavailable_reason,
    }


def is_negative_dashboard_sentiment(ticket: TicketDetailsSummary | object) -> bool:
    return getattr(ticket, "sentiment", None) in {
        TicketSentiment.FRUSTRATED,
        TicketSentiment.ESCALATION_RISK,
    }


def needs_operator_reply(ticket: TicketDetailsSummary | object) -> bool:
    if not isinstance(ticket, TicketDetailsSummary):
        return False
    if ticket.last_message_sender_type == TicketMessageSenderType.CLIENT:
        return True
    return not any(
        message.sender_type == TicketMessageSenderType.OPERATOR
        for message in ticket.message_history
    )


def serialize_archived_ticket(ticket: HistoricalTicketSummary) -> dict[str, Any]:
    return {
        "public_id": str(ticket.public_id),
        "public_number": ticket.public_number,
        "status": ticket.status.value,
        "created_at": _serialize_datetime(ticket.created_at),
        "closed_at": _serialize_datetime(ticket.closed_at),
        "mini_title": ticket.mini_title,
        "category_id": ticket.category_id,
        "category_code": ticket.category_code,
        "category_title": ticket.category_title,
    }


def serialize_ticket_details(ticket: TicketDetailsSummary) -> dict[str, Any]:
    return {
        "public_id": str(ticket.public_id),
        "public_number": ticket.public_number,
        "client_chat_id": ticket.client_chat_id,
        "status": ticket.status.value,
        "priority": ticket.priority,
        "subject": ticket.subject,
        "assigned_operator_id": ticket.assigned_operator_id,
        "assigned_operator_name": ticket.assigned_operator_name,
        "assigned_operator_telegram_user_id": ticket.assigned_operator_telegram_user_id,
        "assigned_operator_username": ticket.assigned_operator_username,
        "created_at": _serialize_datetime(ticket.created_at),
        "closed_at": _serialize_datetime(ticket.closed_at),
        "category_id": ticket.category_id,
        "category_code": ticket.category_code,
        "category_title": ticket.category_title,
        "sentiment": ticket.sentiment.value if ticket.sentiment is not None else None,
        "sentiment_confidence": (
            ticket.sentiment_confidence.value if ticket.sentiment_confidence is not None else None
        ),
        "sentiment_reason": ticket.sentiment_reason,
        "sentiment_detected_at": _serialize_datetime(ticket.sentiment_detected_at),
        "tags": list(ticket.tags),
        "last_message_text": ticket.last_message_text,
        "last_message_sender_type": (
            ticket.last_message_sender_type.value if ticket.last_message_sender_type else None
        ),
        "last_message_attachment": serialize_attachment(ticket.last_message_attachment),
        "message_history": [
            {
                "sender_type": message.sender_type.value,
                "sender_operator_id": message.sender_operator_id,
                "sender_operator_name": message.sender_operator_name,
                "text": message.text,
                "created_at": _serialize_datetime(message.created_at),
                "attachment": serialize_attachment(message.attachment),
                "sentiment": message.sentiment.value if message.sentiment else None,
                "sentiment_confidence": (
                    message.sentiment_confidence.value
                    if message.sentiment_confidence is not None
                    else None
                ),
                "sentiment_reason": message.sentiment_reason,
                "duplicate_count": message.duplicate_count,
                "last_duplicate_at": _serialize_datetime(message.last_duplicate_at),
            }
            for message in ticket.message_history
        ],
        "internal_notes": [
            {
                "id": note.id,
                "author_operator_id": note.author_operator_id,
                "author_operator_name": note.author_operator_name,
                "text": note.text,
                "created_at": _serialize_datetime(note.created_at),
            }
            for note in ticket.internal_notes
        ],
    }


def serialize_ticket_timeline(
    ticket: TicketDetailsSummary | None,
    ai_snapshot: TicketAssistSnapshot | None = None,
) -> dict[str, Any]:
    if ticket is None:
        return {"items": [], "warning": "Ticket history is temporarily unavailable."}

    items: list[dict[str, Any]] = [
        _build_timeline_item(
            item_id="ticket-created",
            item_type="ticket_created",
            title="Ticket created",
            description=f"{ticket.public_number} was opened.",
            actor_label="Customer",
            created_at=ticket.created_at,
            metadata={
                "status": ticket.status.value,
                "priority": ticket.priority,
                "category": ticket.category_title,
            },
        )
    ]

    if ticket.assigned_operator_name:
        items.append(
            _build_timeline_item(
                item_id="ticket-current-assignment",
                item_type="ticket_assigned",
                title="Current assignment",
                description=f"Ticket is assigned to {ticket.assigned_operator_name}.",
                actor_label=ticket.assigned_operator_name,
                created_at=ticket.created_at,
                metadata={"derived": True},
            )
        )

    for index, message in enumerate(ticket.message_history, start=1):
        is_operator = message.sender_type.value == "operator"
        has_attachment = message.attachment is not None
        text = _clip_timeline_text(message.text)
        if text is None and has_attachment:
            text = "Attachment added."
        items.append(
            _build_timeline_item(
                item_id=f"message-{index}",
                item_type="operator_reply" if is_operator else "message_received",
                title="Operator replied" if is_operator else "Customer message received",
                description=text or "Message without text.",
                actor_label=(
                    message.sender_operator_name
                    if is_operator and message.sender_operator_name
                    else ("Operator" if is_operator else "Customer")
                ),
                created_at=message.created_at,
                metadata=(
                    {
                        "attachment_kind": message.attachment.kind.value,
                        "attachment_filename": message.attachment.filename,
                    }
                    if has_attachment and message.attachment is not None
                    else None
                ),
            )
        )

    for note in ticket.internal_notes:
        items.append(
            _build_timeline_item(
                item_id=f"note-{note.id}",
                item_type="internal_note_added",
                title="Internal note added",
                description=_clip_timeline_text(note.text) or "Internal note added.",
                actor_label=note.author_operator_name or "Operator",
                created_at=note.created_at,
                metadata=None,
            )
        )

    if ai_snapshot is not None and ai_snapshot.summary_generated_at is not None:
        items.append(
            _build_timeline_item(
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
        )

    if ticket.closed_at is not None:
        items.append(
            _build_timeline_item(
                item_id="ticket-closed",
                item_type="ticket_closed",
                title="Ticket closed",
                description=f"{ticket.public_number} was closed.",
                actor_label=ticket.assigned_operator_name or "Operator",
                created_at=ticket.closed_at,
                metadata={"status": "closed"},
            )
        )

    return {
        "items": sorted(items, key=lambda item: (item["created_at"] or "", item["id"])),
        "warning": None,
    }


def serialize_attachment(attachment: TicketAttachmentSummary | None) -> dict[str, Any] | None:
    if attachment is None:
        return None
    return {
        "kind": attachment.kind.value,
        "telegram_file_id": attachment.telegram_file_id,
        "telegram_file_unique_id": attachment.telegram_file_unique_id,
        "filename": attachment.filename,
        "mime_type": attachment.mime_type,
        "storage_path": attachment.storage_path,
    }


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
        "created_at": _serialize_datetime(created_at),
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


def serialize_ticket_ai_snapshot(snapshot: TicketAssistSnapshot | None) -> dict[str, Any] | None:
    if snapshot is None:
        return None
    return {
        "available": snapshot.available,
        "unavailable_reason": snapshot.unavailable_reason,
        "model_id": snapshot.model_id,
        "short_summary": snapshot.short_summary,
        "user_goal": snapshot.user_goal,
        "actions_taken": snapshot.actions_taken,
        "current_status": snapshot.current_status,
        "summary_status": snapshot.summary_status.value,
        "summary_generated_at": _serialize_datetime(snapshot.summary_generated_at),
        "status_note": snapshot.status_note,
        "macro_suggestions": [
            {
                "macro_id": item.macro_id,
                "title": item.title,
                "body": item.body,
                "reason": item.reason,
                "confidence": item.confidence.value,
            }
            for item in snapshot.macro_suggestions
        ],
    }


def serialize_ticket_reply_draft(draft: TicketReplyDraft | None) -> dict[str, Any] | None:
    if draft is None:
        return None
    return {
        "available": draft.available,
        "reply_text": draft.reply_text,
        "tone": draft.tone,
        "confidence": draft.confidence,
        "safety_note": draft.safety_note,
        "missing_information": (
            list(draft.missing_information) if draft.missing_information is not None else None
        ),
        "unavailable_reason": draft.unavailable_reason,
        "model_id": draft.model_id,
    }


def serialize_macro(macro: MacroSummary) -> dict[str, Any]:
    return {
        "id": macro.id,
        "title": macro.title,
        "body": macro.body,
    }


def serialize_operator(operator: OperatorSummary) -> dict[str, Any]:
    return {
        "telegram_user_id": operator.telegram_user_id,
        "display_name": operator.display_name,
        "username": operator.username,
        "is_active": operator.is_active,
    }


def serialize_operator_invite(invite: OperatorInviteCodeSummary) -> dict[str, Any]:
    return {
        "code": invite.code,
        "expires_at": _serialize_datetime(invite.expires_at),
        "max_uses": invite.max_uses,
    }


def serialize_analytics_snapshot(snapshot: HelpdeskAnalyticsSnapshot) -> dict[str, Any]:
    return {
        "window": snapshot.window.value,
        "total_open_tickets": snapshot.total_open_tickets,
        "queued_tickets_count": snapshot.queued_tickets_count,
        "assigned_tickets_count": snapshot.assigned_tickets_count,
        "escalated_tickets_count": snapshot.escalated_tickets_count,
        "closed_tickets_count": snapshot.closed_tickets_count,
        "period_created_tickets_count": snapshot.period_created_tickets_count,
        "period_closed_tickets_count": snapshot.period_closed_tickets_count,
        "average_first_response_time_seconds": snapshot.average_first_response_time_seconds,
        "average_resolution_time_seconds": snapshot.average_resolution_time_seconds,
        "satisfaction_average": snapshot.satisfaction_average,
        "feedback_count": snapshot.feedback_count,
        "feedback_coverage_percent": snapshot.feedback_coverage_percent,
        "tickets_per_operator": [
            {
                "operator_id": item.operator_id,
                "display_name": item.display_name,
                "ticket_count": item.ticket_count,
            }
            for item in snapshot.tickets_per_operator
        ],
        "rating_distribution": [
            {
                "rating": bucket.rating,
                "count": bucket.count,
            }
            for bucket in snapshot.rating_distribution
        ],
        "operator_snapshots": [
            {
                "operator_id": item.operator_id,
                "display_name": item.display_name,
                "active_ticket_count": item.active_ticket_count,
                "closed_ticket_count": item.closed_ticket_count,
                "average_first_response_time_seconds": item.average_first_response_time_seconds,
                "average_resolution_time_seconds": item.average_resolution_time_seconds,
                "average_satisfaction": item.average_satisfaction,
                "feedback_count": item.feedback_count,
            }
            for item in snapshot.operator_snapshots
        ],
        "category_snapshots": [
            {
                "category_id": item.category_id,
                "category_title": item.category_title,
                "created_ticket_count": item.created_ticket_count,
                "open_ticket_count": item.open_ticket_count,
                "closed_ticket_count": item.closed_ticket_count,
                "average_satisfaction": item.average_satisfaction,
                "feedback_count": item.feedback_count,
                "sla_breach_count": item.sla_breach_count,
            }
            for item in snapshot.category_snapshots
        ],
        "best_operators_by_closures": [
            {
                "operator_id": item.operator_id,
                "display_name": item.display_name,
                "active_ticket_count": item.active_ticket_count,
                "closed_ticket_count": item.closed_ticket_count,
                "average_first_response_time_seconds": item.average_first_response_time_seconds,
                "average_resolution_time_seconds": item.average_resolution_time_seconds,
                "average_satisfaction": item.average_satisfaction,
                "feedback_count": item.feedback_count,
            }
            for item in snapshot.best_operators_by_closures
        ],
        "best_operators_by_satisfaction": [
            {
                "operator_id": item.operator_id,
                "display_name": item.display_name,
                "active_ticket_count": item.active_ticket_count,
                "closed_ticket_count": item.closed_ticket_count,
                "average_first_response_time_seconds": item.average_first_response_time_seconds,
                "average_resolution_time_seconds": item.average_resolution_time_seconds,
                "average_satisfaction": item.average_satisfaction,
                "feedback_count": item.feedback_count,
            }
            for item in snapshot.best_operators_by_satisfaction
        ],
        "top_categories": [
            {
                "category_id": item.category_id,
                "category_title": item.category_title,
                "created_ticket_count": item.created_ticket_count,
                "open_ticket_count": item.open_ticket_count,
                "closed_ticket_count": item.closed_ticket_count,
                "average_satisfaction": item.average_satisfaction,
                "feedback_count": item.feedback_count,
                "sla_breach_count": item.sla_breach_count,
            }
            for item in snapshot.top_categories
        ],
        "first_response_breach_count": snapshot.first_response_breach_count,
        "resolution_breach_count": snapshot.resolution_breach_count,
        "sla_categories": [
            {
                "category_id": item.category_id,
                "category_title": item.category_title,
                "created_ticket_count": item.created_ticket_count,
                "open_ticket_count": item.open_ticket_count,
                "closed_ticket_count": item.closed_ticket_count,
                "average_satisfaction": item.average_satisfaction,
                "feedback_count": item.feedback_count,
                "sla_breach_count": item.sla_breach_count,
            }
            for item in snapshot.sla_categories
        ],
    }


def _serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _resolve_ticket_last_activity(
    ticket: TicketDetailsSummary | QueuedTicketSummary | OperatorTicketSummary,
) -> datetime | None:
    if not isinstance(ticket, TicketDetailsSummary):
        return None
    candidates = [ticket.created_at, ticket.closed_at, ticket.sentiment_detected_at]
    candidates.extend(message.created_at for message in ticket.message_history)
    candidates.extend(note.created_at for note in ticket.internal_notes)
    return max((item for item in candidates if item is not None), default=None)


def _ticket_activity_sort_value(
    ticket: TicketDetailsSummary | QueuedTicketSummary | OperatorTicketSummary,
) -> float:
    last_activity = _resolve_ticket_last_activity(ticket)
    if last_activity is None:
        return 0.0
    return last_activity.timestamp()


def _serialize_assigned_operator(
    ticket: TicketDetailsSummary | QueuedTicketSummary | OperatorTicketSummary,
) -> dict[str, Any] | None:
    if not isinstance(ticket, TicketDetailsSummary):
        return None
    if ticket.assigned_operator_id is None and ticket.assigned_operator_name is None:
        return None
    return {
        "id": ticket.assigned_operator_id,
        "name": ticket.assigned_operator_name,
        "telegram_user_id": ticket.assigned_operator_telegram_user_id,
        "username": ticket.assigned_operator_username,
    }


def _serialize_ticket_sentiment(
    ticket: TicketDetailsSummary | QueuedTicketSummary | OperatorTicketSummary,
) -> dict[str, Any] | None:
    if not isinstance(ticket, TicketDetailsSummary) or ticket.sentiment is None:
        return None
    return {
        "value": ticket.sentiment.value,
        "confidence": (
            ticket.sentiment_confidence.value if ticket.sentiment_confidence is not None else None
        ),
        "reason": ticket.sentiment_reason,
        "detected_at": _serialize_datetime(ticket.sentiment_detected_at),
    }


def _serialize_sla_state(ticket: object) -> dict[str, Any] | None:
    state = getattr(ticket, "sla_state", None)
    if isinstance(state, dict):
        return state
    if isinstance(state, str):
        return {"status": state}
    return None
