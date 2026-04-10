from __future__ import annotations

import csv
from datetime import UTC, datetime
from io import StringIO

from application.use_cases.tickets.exports import TicketReport

FIELDNAMES = (
    "ticket_public_number",
    "ticket_public_id",
    "ticket_status",
    "ticket_priority",
    "ticket_subject",
    "ticket_category_code",
    "ticket_category_title",
    "ticket_created_at",
    "ticket_updated_at",
    "ticket_first_response_at",
    "ticket_first_response_seconds",
    "ticket_closed_at",
    "ticket_assigned_operator_id",
    "ticket_assigned_operator_name",
    "ticket_assigned_operator_telegram_user_id",
    "ticket_client_chat_id",
    "ticket_tags",
    "feedback_rating",
    "feedback_comment",
    "feedback_submitted_at",
    "transcript_index",
    "transcript_timestamp",
    "transcript_sender_role",
    "transcript_sender_name",
    "transcript_text",
)


def render_ticket_report_csv(report: TicketReport) -> bytes:
    buffer = StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=FIELDNAMES)
    writer.writeheader()

    if report.messages:
        for index, message in enumerate(report.messages, start=1):
            writer.writerow(
                {
                    **_build_base_row(report),
                    "transcript_index": index,
                    "transcript_timestamp": _format_timestamp(message.created_at),
                    "transcript_sender_role": message.sender_type.value,
                    "transcript_sender_name": message.sender_operator_name or "",
                    "transcript_text": message.text,
                }
            )
    else:
        writer.writerow(_build_base_row(report))

    return buffer.getvalue().encode("utf-8-sig")


def _build_base_row(report: TicketReport) -> dict[str, str | int]:
    return {
        "ticket_public_number": report.public_number,
        "ticket_public_id": str(report.public_id),
        "ticket_status": report.status.value,
        "ticket_priority": report.priority,
        "ticket_subject": report.subject,
        "ticket_category_code": report.category_code or "",
        "ticket_category_title": report.category_title or "",
        "ticket_created_at": _format_timestamp(report.created_at),
        "ticket_updated_at": _format_timestamp(report.updated_at),
        "ticket_first_response_at": _format_timestamp(report.first_response_at),
        "ticket_first_response_seconds": report.first_response_seconds or "",
        "ticket_closed_at": _format_timestamp(report.closed_at),
        "ticket_assigned_operator_id": report.assigned_operator_id or "",
        "ticket_assigned_operator_name": report.assigned_operator_name or "",
        "ticket_assigned_operator_telegram_user_id": (
            report.assigned_operator_telegram_user_id or ""
        ),
        "ticket_client_chat_id": report.client_chat_id,
        "ticket_tags": ", ".join(report.tags),
        "feedback_rating": report.feedback.rating if report.feedback is not None else "",
        "feedback_comment": report.feedback.comment if report.feedback is not None else "",
        "feedback_submitted_at": (
            _format_timestamp(report.feedback.submitted_at) if report.feedback is not None else ""
        ),
        "transcript_index": "",
        "transcript_timestamp": "",
        "transcript_sender_role": "",
        "transcript_sender_name": "",
        "transcript_text": "",
    }


def _format_timestamp(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.astimezone(UTC).isoformat()
