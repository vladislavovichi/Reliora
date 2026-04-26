from __future__ import annotations

from datetime import datetime
from typing import Any

from application.ai.summaries import TicketAssistSnapshot, TicketReplyDraft
from application.services.stats import HelpdeskAnalyticsSnapshot
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


def serialize_access_context(access_context: AccessContextSummary) -> dict[str, Any]:
    return {
        "telegram_user_id": access_context.telegram_user_id,
        "role": access_context.role.value,
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
