# mypy: disable-error-code="attr-defined,name-defined"
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from application.ai.summaries import (
    AIPredictionConfidence,
    TicketAssistSnapshot,
    TicketCategoryPrediction,
    TicketMacroSuggestion,
    TicketReplyDraft,
    TicketSummaryStatus,
)
from application.use_cases.tickets.exports import (
    TicketReport,
    TicketReportExport,
    TicketReportFormat,
)
from application.use_cases.tickets.summaries import (
    HistoricalTicketSummary,
    MacroApplicationResult,
    MacroSummary,
    OperatorReplyResult,
    OperatorTicketSummary,
    QueuedTicketSummary,
    TicketCategorySummary,
    TicketDetailsSummary,
    TicketInternalNoteSummary,
    TicketMessageSummary,
    TicketSummary,
)
from backend.grpc.generated import helpdesk_pb2
from backend.grpc.translators_shared import (
    _deserialize_attachment_summary,
    _deserialize_timestamp,
    _has,
    _serialize_timestamp,
    serialize_attachment,
)
from domain.enums.tickets import (
    TicketMessageSenderType,
    TicketSentiment,
    TicketSignalConfidence,
    TicketStatus,
)


def serialize_ticket_summary(ticket: TicketSummary) -> helpdesk_pb2.TicketSummary:
    message = helpdesk_pb2.TicketSummary(
        public_id=str(ticket.public_id),
        public_number=ticket.public_number,
        status=ticket.status.value,
        created=ticket.created,
    )
    if ticket.event_type is not None:
        message.event_type = ticket.event_type.value
    return message


def deserialize_ticket_summary(ticket: helpdesk_pb2.TicketSummary) -> TicketSummary:
    from domain.enums.tickets import TicketEventType

    return TicketSummary(
        public_id=UUID(ticket.public_id),
        public_number=ticket.public_number,
        status=TicketStatus(ticket.status),
        created=ticket.created,
        event_type=TicketEventType(ticket.event_type) if _has(ticket, "event_type") else None,
    )


def serialize_queued_ticket(ticket: QueuedTicketSummary) -> helpdesk_pb2.QueuedTicketSummary:
    message = helpdesk_pb2.QueuedTicketSummary(
        public_id=str(ticket.public_id),
        public_number=ticket.public_number,
        subject=ticket.subject,
        priority=ticket.priority,
        status=ticket.status.value,
    )
    if ticket.category_title is not None:
        message.category_title = ticket.category_title
    return message


def deserialize_queued_ticket(
    ticket: helpdesk_pb2.QueuedTicketSummary,
) -> QueuedTicketSummary:
    return QueuedTicketSummary(
        public_id=UUID(ticket.public_id),
        public_number=ticket.public_number,
        subject=ticket.subject,
        priority=ticket.priority,
        status=TicketStatus(ticket.status),
        category_title=ticket.category_title if _has(ticket, "category_title") else None,
    )


def serialize_operator_ticket(
    ticket: OperatorTicketSummary,
) -> helpdesk_pb2.OperatorTicketSummary:
    message = helpdesk_pb2.OperatorTicketSummary(
        public_id=str(ticket.public_id),
        public_number=ticket.public_number,
        subject=ticket.subject,
        priority=ticket.priority,
        status=ticket.status.value,
    )
    if ticket.category_title is not None:
        message.category_title = ticket.category_title
    return message


def deserialize_operator_ticket(
    ticket: helpdesk_pb2.OperatorTicketSummary,
) -> OperatorTicketSummary:
    return OperatorTicketSummary(
        public_id=UUID(ticket.public_id),
        public_number=ticket.public_number,
        subject=ticket.subject,
        priority=ticket.priority,
        status=TicketStatus(ticket.status),
        category_title=ticket.category_title if _has(ticket, "category_title") else None,
    )


def serialize_archived_ticket(
    ticket: HistoricalTicketSummary,
) -> helpdesk_pb2.ArchivedTicketSummary:
    message = helpdesk_pb2.ArchivedTicketSummary(
        public_id=str(ticket.public_id),
        public_number=ticket.public_number,
        status=ticket.status.value,
        created_at=_serialize_timestamp(ticket.created_at),
        mini_title=ticket.mini_title,
    )
    if ticket.closed_at is not None:
        message.closed_at.CopyFrom(_serialize_timestamp(ticket.closed_at))
    if ticket.category_id is not None:
        message.category_id = ticket.category_id
    if ticket.category_code is not None:
        message.category_code = ticket.category_code
    if ticket.category_title is not None:
        message.category_title = ticket.category_title
    return message


def deserialize_archived_ticket(
    ticket: helpdesk_pb2.ArchivedTicketSummary,
) -> HistoricalTicketSummary:
    return HistoricalTicketSummary(
        public_id=UUID(ticket.public_id),
        public_number=ticket.public_number,
        status=TicketStatus(ticket.status),
        created_at=_deserialize_timestamp(ticket.created_at),
        closed_at=_deserialize_timestamp(ticket.closed_at)
        if ticket.HasField("closed_at")
        else None,
        mini_title=ticket.mini_title,
        category_id=ticket.category_id if _has(ticket, "category_id") else None,
        category_code=ticket.category_code if _has(ticket, "category_code") else None,
        category_title=ticket.category_title if _has(ticket, "category_title") else None,
    )


def serialize_ticket_assist_snapshot(
    snapshot: TicketAssistSnapshot,
) -> helpdesk_pb2.TicketAssistSnapshot:
    message = helpdesk_pb2.TicketAssistSnapshot(available=snapshot.available)
    if snapshot.unavailable_reason is not None:
        message.unavailable_reason = snapshot.unavailable_reason
    if snapshot.model_id is not None:
        message.model_id = snapshot.model_id
    if snapshot.short_summary is not None:
        message.short_summary = snapshot.short_summary
    if snapshot.user_goal is not None:
        message.user_goal = snapshot.user_goal
    if snapshot.actions_taken is not None:
        message.actions_taken = snapshot.actions_taken
    if snapshot.current_status is not None:
        message.current_status = snapshot.current_status
    if snapshot.summary_status is not None:
        message.summary_status = snapshot.summary_status.value
    if snapshot.summary_generated_at is not None:
        message.summary_generated_at.CopyFrom(_serialize_timestamp(snapshot.summary_generated_at))
    if snapshot.status_note is not None:
        message.status_note = snapshot.status_note
    message.macro_suggestions.extend(
        helpdesk_pb2.TicketAssistMacroSuggestion(
            macro_id=item.macro_id,
            title=item.title,
            body=item.body,
            reason=item.reason,
            confidence=item.confidence.value,
        )
        for item in snapshot.macro_suggestions
    )
    return message


def deserialize_ticket_assist_snapshot(
    snapshot: helpdesk_pb2.TicketAssistSnapshot,
) -> TicketAssistSnapshot:
    return TicketAssistSnapshot(
        available=snapshot.available,
        summary_status=(
            TicketSummaryStatus(snapshot.summary_status)
            if _has(snapshot, "summary_status")
            else TicketSummaryStatus.MISSING
        ),
        summary_generated_at=(
            _deserialize_timestamp(snapshot.summary_generated_at)
            if snapshot.HasField("summary_generated_at")
            else None
        ),
        unavailable_reason=(
            snapshot.unavailable_reason if _has(snapshot, "unavailable_reason") else None
        ),
        model_id=snapshot.model_id if _has(snapshot, "model_id") else None,
        short_summary=snapshot.short_summary if _has(snapshot, "short_summary") else None,
        user_goal=snapshot.user_goal if _has(snapshot, "user_goal") else None,
        actions_taken=snapshot.actions_taken if _has(snapshot, "actions_taken") else None,
        current_status=snapshot.current_status if _has(snapshot, "current_status") else None,
        status_note=snapshot.status_note if _has(snapshot, "status_note") else None,
        macro_suggestions=tuple(
            TicketMacroSuggestion(
                macro_id=item.macro_id,
                title=item.title,
                body=item.body,
                reason=item.reason,
                confidence=(
                    AIPredictionConfidence(item.confidence)
                    if item.confidence
                    else AIPredictionConfidence.MEDIUM
                ),
            )
            for item in snapshot.macro_suggestions
        ),
    )


def serialize_ticket_reply_draft(draft: TicketReplyDraft) -> helpdesk_pb2.TicketReplyDraft:
    message = helpdesk_pb2.TicketReplyDraft(available=draft.available)
    if draft.reply_text is not None:
        message.reply_text = draft.reply_text
    if draft.tone is not None:
        message.tone = draft.tone
    if draft.confidence is not None:
        message.confidence = draft.confidence
    if draft.safety_note is not None:
        message.safety_note = draft.safety_note
    if draft.missing_information is not None:
        message.missing_information.extend(draft.missing_information)
    if draft.unavailable_reason is not None:
        message.unavailable_reason = draft.unavailable_reason
    if draft.model_id is not None:
        message.model_id = draft.model_id
    return message


def deserialize_ticket_reply_draft(draft: helpdesk_pb2.TicketReplyDraft) -> TicketReplyDraft:
    return TicketReplyDraft(
        available=draft.available,
        reply_text=draft.reply_text if _has(draft, "reply_text") else None,
        tone=draft.tone if _has(draft, "tone") else None,
        confidence=draft.confidence if _has(draft, "confidence") else None,
        safety_note=draft.safety_note if _has(draft, "safety_note") else None,
        missing_information=(
            tuple(draft.missing_information) if draft.missing_information else None
        ),
        unavailable_reason=draft.unavailable_reason if _has(draft, "unavailable_reason") else None,
        model_id=draft.model_id if _has(draft, "model_id") else None,
    )


def serialize_ticket_category_prediction(
    prediction: TicketCategoryPrediction,
) -> helpdesk_pb2.TicketCategoryPrediction:
    message = helpdesk_pb2.TicketCategoryPrediction(
        available=prediction.available,
        confidence=prediction.confidence.value,
    )
    if prediction.category_id is not None:
        message.category_id = prediction.category_id
    if prediction.category_code is not None:
        message.category_code = prediction.category_code
    if prediction.category_title is not None:
        message.category_title = prediction.category_title
    if prediction.reason is not None:
        message.reason = prediction.reason
    if prediction.model_id is not None:
        message.model_id = prediction.model_id
    return message


def deserialize_ticket_category_prediction(
    prediction: helpdesk_pb2.TicketCategoryPrediction,
) -> TicketCategoryPrediction:
    return TicketCategoryPrediction(
        available=prediction.available,
        category_id=prediction.category_id if _has(prediction, "category_id") else None,
        category_code=prediction.category_code if _has(prediction, "category_code") else None,
        category_title=prediction.category_title if _has(prediction, "category_title") else None,
        confidence=AIPredictionConfidence(prediction.confidence),
        reason=prediction.reason if _has(prediction, "reason") else None,
        model_id=prediction.model_id if _has(prediction, "model_id") else None,
    )


def serialize_category(
    category: TicketCategorySummary,
) -> helpdesk_pb2.TicketCategorySummary:
    return helpdesk_pb2.TicketCategorySummary(
        id=category.id,
        code=category.code,
        title=category.title,
        is_active=category.is_active,
        sort_order=category.sort_order,
    )


def deserialize_category(
    category: helpdesk_pb2.TicketCategorySummary,
) -> TicketCategorySummary:
    return TicketCategorySummary(
        id=category.id,
        code=category.code,
        title=category.title,
        is_active=category.is_active,
        sort_order=category.sort_order,
    )


def serialize_ticket_message(
    message: TicketMessageSummary,
) -> helpdesk_pb2.TicketMessageSummary:
    result = helpdesk_pb2.TicketMessageSummary(
        sender_type=message.sender_type.value,
        created_at=_serialize_timestamp(message.created_at),
    )
    if message.sender_operator_id is not None:
        result.sender_operator_id = message.sender_operator_id
    if message.sender_operator_name is not None:
        result.sender_operator_name = message.sender_operator_name
    if message.text is not None:
        result.text = message.text
    if message.attachment is not None:
        result.attachment.CopyFrom(serialize_attachment(message.attachment))
    if message.sentiment is not None:
        result.sentiment = message.sentiment.value
    if message.sentiment_confidence is not None:
        result.sentiment_confidence = message.sentiment_confidence.value
    if message.sentiment_reason is not None:
        result.sentiment_reason = message.sentiment_reason
    result.duplicate_count = message.duplicate_count
    if message.last_duplicate_at is not None:
        result.last_duplicate_at.CopyFrom(_serialize_timestamp(message.last_duplicate_at))
    return result


def deserialize_ticket_message(
    message: helpdesk_pb2.TicketMessageSummary,
) -> TicketMessageSummary:
    return TicketMessageSummary(
        sender_type=TicketMessageSenderType(message.sender_type),
        sender_operator_id=(
            message.sender_operator_id if _has(message, "sender_operator_id") else None
        ),
        sender_operator_name=(
            message.sender_operator_name if _has(message, "sender_operator_name") else None
        ),
        text=message.text if _has(message, "text") else None,
        created_at=_deserialize_timestamp(message.created_at),
        attachment=(
            _deserialize_attachment_summary(message.attachment)
            if message.HasField("attachment")
            else None
        ),
        sentiment=TicketSentiment(message.sentiment) if _has(message, "sentiment") else None,
        sentiment_confidence=(
            TicketSignalConfidence(message.sentiment_confidence)
            if _has(message, "sentiment_confidence")
            else None
        ),
        sentiment_reason=message.sentiment_reason if _has(message, "sentiment_reason") else None,
        duplicate_count=message.duplicate_count,
        last_duplicate_at=(
            _deserialize_timestamp(message.last_duplicate_at)
            if message.HasField("last_duplicate_at")
            else None
        ),
    )


def serialize_ticket_note(
    note: TicketInternalNoteSummary,
) -> helpdesk_pb2.TicketInternalNoteSummary:
    message = helpdesk_pb2.TicketInternalNoteSummary(
        id=note.id,
        author_operator_id=note.author_operator_id,
        text=note.text,
        created_at=_serialize_timestamp(note.created_at),
    )
    if note.author_operator_name is not None:
        message.author_operator_name = note.author_operator_name
    return message


def deserialize_ticket_note(
    note: helpdesk_pb2.TicketInternalNoteSummary,
) -> TicketInternalNoteSummary:
    return TicketInternalNoteSummary(
        id=note.id,
        author_operator_id=note.author_operator_id,
        author_operator_name=(
            note.author_operator_name if _has(note, "author_operator_name") else None
        ),
        text=note.text,
        created_at=_deserialize_timestamp(note.created_at),
    )


def serialize_ticket_details(
    ticket: TicketDetailsSummary,
) -> helpdesk_pb2.TicketDetailsSummary:
    message = helpdesk_pb2.TicketDetailsSummary(
        public_id=str(ticket.public_id),
        public_number=ticket.public_number,
        client_chat_id=ticket.client_chat_id,
        status=ticket.status.value,
        priority=ticket.priority,
        subject=ticket.subject,
        created_at=_serialize_timestamp(ticket.created_at),
        tags=ticket.tags,
    )
    if ticket.closed_at is not None:
        message.closed_at.CopyFrom(_serialize_timestamp(ticket.closed_at))
    if ticket.assigned_operator_id is not None:
        message.assigned_operator_id = ticket.assigned_operator_id
    if ticket.assigned_operator_name is not None:
        message.assigned_operator_name = ticket.assigned_operator_name
    if ticket.assigned_operator_telegram_user_id is not None:
        message.assigned_operator_telegram_user_id = ticket.assigned_operator_telegram_user_id
    if ticket.category_id is not None:
        message.category_id = ticket.category_id
    if ticket.category_code is not None:
        message.category_code = ticket.category_code
    if ticket.category_title is not None:
        message.category_title = ticket.category_title
    if ticket.last_message_text is not None:
        message.last_message_text = ticket.last_message_text
    if ticket.last_message_sender_type is not None:
        message.last_message_sender_type = ticket.last_message_sender_type.value
    if ticket.last_message_attachment is not None:
        message.last_message_attachment.CopyFrom(
            serialize_attachment(ticket.last_message_attachment)
        )
    if ticket.sentiment is not None:
        message.sentiment = ticket.sentiment.value
    if ticket.sentiment_confidence is not None:
        message.sentiment_confidence = ticket.sentiment_confidence.value
    if ticket.sentiment_reason is not None:
        message.sentiment_reason = ticket.sentiment_reason
    if ticket.sentiment_detected_at is not None:
        message.sentiment_detected_at.CopyFrom(_serialize_timestamp(ticket.sentiment_detected_at))
    message.message_history.extend(
        serialize_ticket_message(item) for item in ticket.message_history
    )
    message.internal_notes.extend(serialize_ticket_note(item) for item in ticket.internal_notes)
    return message


def deserialize_ticket_details(
    ticket: helpdesk_pb2.TicketDetailsSummary,
) -> TicketDetailsSummary:
    return TicketDetailsSummary(
        public_id=UUID(ticket.public_id),
        public_number=ticket.public_number,
        client_chat_id=ticket.client_chat_id,
        status=TicketStatus(ticket.status),
        priority=ticket.priority,
        subject=ticket.subject,
        assigned_operator_id=(
            ticket.assigned_operator_id if _has(ticket, "assigned_operator_id") else None
        ),
        assigned_operator_name=(
            ticket.assigned_operator_name if _has(ticket, "assigned_operator_name") else None
        ),
        assigned_operator_telegram_user_id=(
            ticket.assigned_operator_telegram_user_id
            if _has(ticket, "assigned_operator_telegram_user_id")
            else None
        ),
        created_at=_deserialize_timestamp(ticket.created_at),
        closed_at=_deserialize_timestamp(ticket.closed_at)
        if ticket.HasField("closed_at")
        else None,
        category_id=ticket.category_id if _has(ticket, "category_id") else None,
        category_code=ticket.category_code if _has(ticket, "category_code") else None,
        category_title=ticket.category_title if _has(ticket, "category_title") else None,
        sentiment=TicketSentiment(ticket.sentiment) if _has(ticket, "sentiment") else None,
        sentiment_confidence=(
            TicketSignalConfidence(ticket.sentiment_confidence)
            if _has(ticket, "sentiment_confidence")
            else None
        ),
        sentiment_reason=ticket.sentiment_reason if _has(ticket, "sentiment_reason") else None,
        sentiment_detected_at=(
            _deserialize_timestamp(ticket.sentiment_detected_at)
            if ticket.HasField("sentiment_detected_at")
            else None
        ),
        tags=tuple(ticket.tags),
        last_message_text=ticket.last_message_text if _has(ticket, "last_message_text") else None,
        last_message_sender_type=(
            TicketMessageSenderType(ticket.last_message_sender_type)
            if _has(ticket, "last_message_sender_type")
            else None
        ),
        last_message_attachment=(
            _deserialize_attachment_summary(ticket.last_message_attachment)
            if ticket.HasField("last_message_attachment")
            else None
        ),
        message_history=tuple(deserialize_ticket_message(item) for item in ticket.message_history),
        internal_notes=tuple(deserialize_ticket_note(item) for item in ticket.internal_notes),
    )


def serialize_operator_reply_result(
    result: OperatorReplyResult,
) -> helpdesk_pb2.OperatorReplyResult:
    message = helpdesk_pb2.OperatorReplyResult(client_chat_id=result.client_chat_id)
    message.ticket.CopyFrom(serialize_ticket_summary(result.ticket))
    return message


def deserialize_operator_reply_result(
    result: helpdesk_pb2.OperatorReplyResult,
) -> OperatorReplyResult:
    return OperatorReplyResult(
        ticket=deserialize_ticket_summary(result.ticket),
        client_chat_id=result.client_chat_id,
    )


def serialize_macro(macro: MacroSummary) -> helpdesk_pb2.MacroSummary:
    return helpdesk_pb2.MacroSummary(id=macro.id, title=macro.title, body=macro.body)


def deserialize_macro(macro: helpdesk_pb2.MacroSummary) -> MacroSummary:
    return MacroSummary(id=macro.id, title=macro.title, body=macro.body)


def serialize_macro_application_result(
    result: MacroApplicationResult,
) -> helpdesk_pb2.MacroApplicationResult:
    message = helpdesk_pb2.MacroApplicationResult(client_chat_id=result.client_chat_id)
    message.ticket.CopyFrom(serialize_ticket_summary(result.ticket))
    message.macro.CopyFrom(serialize_macro(result.macro))
    return message


def deserialize_macro_application_result(
    result: helpdesk_pb2.MacroApplicationResult,
) -> MacroApplicationResult:
    return MacroApplicationResult(
        ticket=deserialize_ticket_summary(result.ticket),
        client_chat_id=result.client_chat_id,
        macro=deserialize_macro(result.macro),
    )


def serialize_export(export: TicketReportExport) -> helpdesk_pb2.TicketReportExport:
    return helpdesk_pb2.TicketReportExport(
        format=export.format.value,
        filename=export.filename,
        content_type=export.content_type,
        content=export.content,
        report_public_number=export.report.public_number,
    )


def deserialize_export(export: helpdesk_pb2.TicketReportExport) -> TicketReportExport:
    placeholder_time = datetime(1970, 1, 1, tzinfo=UTC)
    placeholder_report = TicketReport(
        public_id=UUID(int=0),
        public_number=export.report_public_number,
        client_chat_id=0,
        status=TicketStatus.CLOSED,
        priority="normal",
        subject="",
        assigned_operator_id=None,
        assigned_operator_name=None,
        assigned_operator_telegram_user_id=None,
        created_at=placeholder_time,
        updated_at=placeholder_time,
        first_response_at=None,
        first_response_seconds=None,
        closed_at=None,
        category_code=None,
        category_title=None,
        sentiment=None,
        sentiment_confidence=None,
        sentiment_reason=None,
        sentiment_detected_at=None,
        tags=(),
        feedback=None,
        messages=(),
        events=(),
    )
    return TicketReportExport(
        format=TicketReportFormat(export.format),
        filename=export.filename,
        content_type=export.content_type,
        content=export.content,
        report=placeholder_report,
    )
