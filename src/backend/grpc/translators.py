# mypy: disable-error-code="attr-defined,name-defined"
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from google.protobuf.timestamp_pb2 import Timestamp

from application.ai.summaries import (
    AIPredictionConfidence,
    TicketAssistSnapshot,
    TicketCategoryPrediction,
    TicketMacroSuggestion,
    TicketSummaryStatus,
)
from application.contracts.actors import OperatorIdentity, RequestActor
from application.contracts.ai import PredictTicketCategoryCommand
from application.contracts.tickets import (
    ApplyMacroToTicketCommand,
    AssignNextQueuedTicketCommand,
    ClientTicketMessageCommand,
    OperatorTicketReplyCommand,
    TicketAssignmentCommand,
)
from application.services.stats import (
    AnalyticsCategorySnapshot,
    AnalyticsOperatorSnapshot,
    AnalyticsRatingBucket,
    AnalyticsWindow,
    HelpdeskAnalyticsSnapshot,
    OperatorTicketLoad,
)
from application.use_cases.analytics.exports import (
    AnalyticsExportFormat,
    AnalyticsSection,
    AnalyticsSnapshotExport,
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
    TicketAttachmentSummary,
    TicketCategorySummary,
    TicketDetailsSummary,
    TicketInternalNoteSummary,
    TicketMessageSummary,
    TicketSummary,
)
from backend.grpc.generated import helpdesk_pb2
from domain.entities.ticket import TicketAttachmentDetails
from domain.enums.tickets import TicketAttachmentKind, TicketMessageSenderType, TicketStatus


def serialize_request_actor(actor: RequestActor) -> helpdesk_pb2.RequestActor:
    return helpdesk_pb2.RequestActor(telegram_user_id=actor.telegram_user_id)


def deserialize_request_actor(actor: helpdesk_pb2.RequestActor | None) -> RequestActor | None:
    if actor is None:
        return None
    return RequestActor(telegram_user_id=actor.telegram_user_id)


def serialize_operator_identity(operator: OperatorIdentity) -> helpdesk_pb2.OperatorIdentity:
    message = helpdesk_pb2.OperatorIdentity(
        telegram_user_id=operator.telegram_user_id,
        display_name=operator.display_name,
    )
    if operator.username is not None:
        message.username = operator.username
    return message


def deserialize_operator_identity(operator: helpdesk_pb2.OperatorIdentity) -> OperatorIdentity:
    return OperatorIdentity(
        telegram_user_id=operator.telegram_user_id,
        display_name=operator.display_name,
        username=operator.username if _has(operator, "username") else None,
    )


def serialize_attachment(
    attachment: TicketAttachmentDetails | TicketAttachmentSummary | None,
) -> helpdesk_pb2.TicketAttachment | None:
    if attachment is None:
        return None

    message = helpdesk_pb2.TicketAttachment(
        kind=attachment.kind.value,
        telegram_file_id=attachment.telegram_file_id,
    )
    if attachment.telegram_file_unique_id is not None:
        message.telegram_file_unique_id = attachment.telegram_file_unique_id
    if attachment.filename is not None:
        message.filename = attachment.filename
    if attachment.mime_type is not None:
        message.mime_type = attachment.mime_type
    if attachment.storage_path is not None:
        message.storage_path = attachment.storage_path
    return message


def deserialize_attachment(
    attachment: helpdesk_pb2.TicketAttachment | None,
) -> TicketAttachmentDetails | None:
    if attachment is None:
        return None

    return TicketAttachmentDetails(
        kind=TicketAttachmentKind(attachment.kind),
        telegram_file_id=attachment.telegram_file_id,
        telegram_file_unique_id=(
            attachment.telegram_file_unique_id
            if _has(attachment, "telegram_file_unique_id")
            else None
        ),
        filename=attachment.filename if _has(attachment, "filename") else None,
        mime_type=attachment.mime_type if _has(attachment, "mime_type") else None,
        storage_path=attachment.storage_path if _has(attachment, "storage_path") else None,
    )


def serialize_client_ticket_message_command(
    command: ClientTicketMessageCommand,
) -> helpdesk_pb2.ClientTicketMessageCommand:
    message = helpdesk_pb2.ClientTicketMessageCommand(
        client_chat_id=command.client_chat_id,
        telegram_message_id=command.telegram_message_id,
    )
    if command.text is not None:
        message.text = command.text
    if command.attachment is not None:
        message.attachment.CopyFrom(serialize_attachment(command.attachment))
    if command.category_id is not None:
        message.category_id = command.category_id
    return message


def deserialize_client_ticket_message_command(
    command: helpdesk_pb2.ClientTicketMessageCommand,
) -> ClientTicketMessageCommand:
    return ClientTicketMessageCommand(
        client_chat_id=command.client_chat_id,
        telegram_message_id=command.telegram_message_id,
        text=command.text if _has(command, "text") else None,
        attachment=(
            deserialize_attachment(command.attachment) if command.HasField("attachment") else None
        ),
        category_id=command.category_id if _has(command, "category_id") else None,
    )


def serialize_operator_reply_command(
    command: OperatorTicketReplyCommand,
) -> helpdesk_pb2.OperatorTicketReplyCommand:
    message = helpdesk_pb2.OperatorTicketReplyCommand(
        ticket_public_id=str(command.ticket_public_id),
        telegram_message_id=command.telegram_message_id,
    )
    message.operator.CopyFrom(serialize_operator_identity(command.operator))
    if command.text is not None:
        message.text = command.text
    if command.attachment is not None:
        message.attachment.CopyFrom(serialize_attachment(command.attachment))
    return message


def deserialize_operator_reply_command(
    command: helpdesk_pb2.OperatorTicketReplyCommand,
) -> OperatorTicketReplyCommand:
    return OperatorTicketReplyCommand(
        ticket_public_id=UUID(command.ticket_public_id),
        operator=deserialize_operator_identity(command.operator),
        telegram_message_id=command.telegram_message_id,
        text=command.text if _has(command, "text") else None,
        attachment=(
            deserialize_attachment(command.attachment) if command.HasField("attachment") else None
        ),
    )


def serialize_ticket_assignment_command(
    command: TicketAssignmentCommand,
) -> helpdesk_pb2.TicketAssignmentCommand:
    message = helpdesk_pb2.TicketAssignmentCommand(ticket_public_id=str(command.ticket_public_id))
    message.operator.CopyFrom(serialize_operator_identity(command.operator))
    return message


def deserialize_ticket_assignment_command(
    command: helpdesk_pb2.TicketAssignmentCommand,
) -> TicketAssignmentCommand:
    return TicketAssignmentCommand(
        ticket_public_id=UUID(command.ticket_public_id),
        operator=deserialize_operator_identity(command.operator),
    )


def serialize_assign_next_command(
    command: AssignNextQueuedTicketCommand,
) -> helpdesk_pb2.AssignNextQueuedTicketCommand:
    message = helpdesk_pb2.AssignNextQueuedTicketCommand(
        prioritize_priority=command.prioritize_priority
    )
    message.operator.CopyFrom(serialize_operator_identity(command.operator))
    return message


def deserialize_assign_next_command(
    command: helpdesk_pb2.AssignNextQueuedTicketCommand,
) -> AssignNextQueuedTicketCommand:
    return AssignNextQueuedTicketCommand(
        operator=deserialize_operator_identity(command.operator),
        prioritize_priority=command.prioritize_priority,
    )


def serialize_apply_macro_command(
    command: ApplyMacroToTicketCommand,
) -> helpdesk_pb2.ApplyMacroToTicketCommand:
    message = helpdesk_pb2.ApplyMacroToTicketCommand(
        ticket_public_id=str(command.ticket_public_id),
        macro_id=command.macro_id,
    )
    message.operator.CopyFrom(serialize_operator_identity(command.operator))
    return message


def deserialize_apply_macro_command(
    command: helpdesk_pb2.ApplyMacroToTicketCommand,
) -> ApplyMacroToTicketCommand:
    return ApplyMacroToTicketCommand(
        ticket_public_id=UUID(command.ticket_public_id),
        macro_id=command.macro_id,
        operator=deserialize_operator_identity(command.operator),
    )


def serialize_predict_ticket_category_command(
    command: PredictTicketCategoryCommand,
) -> helpdesk_pb2.PredictTicketCategoryCommand:
    message = helpdesk_pb2.PredictTicketCategoryCommand()
    if command.text is not None:
        message.text = command.text
    if command.attachment_kind is not None:
        message.attachment_kind = command.attachment_kind.value
    if command.attachment_filename is not None:
        message.attachment_filename = command.attachment_filename
    if command.attachment_mime_type is not None:
        message.attachment_mime_type = command.attachment_mime_type
    return message


def deserialize_predict_ticket_category_command(
    command: helpdesk_pb2.PredictTicketCategoryCommand,
) -> PredictTicketCategoryCommand:
    return PredictTicketCategoryCommand(
        text=command.text if _has(command, "text") else None,
        attachment_kind=TicketAttachmentKind(command.attachment_kind)
        if _has(command, "attachment_kind")
        else None,
        attachment_filename=(
            command.attachment_filename if _has(command, "attachment_filename") else None
        ),
        attachment_mime_type=(
            command.attachment_mime_type if _has(command, "attachment_mime_type") else None
        ),
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
        [
            helpdesk_pb2.TicketAssistMacroSuggestion(
                macro_id=item.macro_id,
                title=item.title,
                body=item.body,
                reason=item.reason,
                confidence=item.confidence.value,
            )
            for item in snapshot.macro_suggestions
        ]
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
    from domain.enums.tickets import TicketStatus

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


def serialize_analytics_export(
    export: AnalyticsSnapshotExport,
) -> helpdesk_pb2.AnalyticsReportExport:
    return helpdesk_pb2.AnalyticsReportExport(
        format=export.format.value,
        filename=export.filename,
        content_type=export.content_type,
        content=export.content,
        section=export.section.value,
        window=export.window.value,
    )


def deserialize_analytics_export(
    export: helpdesk_pb2.AnalyticsReportExport,
) -> AnalyticsSnapshotExport:
    return AnalyticsSnapshotExport(
        format=AnalyticsExportFormat(export.format),
        filename=export.filename,
        content_type=export.content_type,
        content=export.content,
        section=AnalyticsSection(export.section),
        window=AnalyticsWindow(export.window),
    )


def serialize_analytics_snapshot(
    snapshot: HelpdeskAnalyticsSnapshot,
) -> helpdesk_pb2.HelpdeskAnalyticsSnapshot:
    message = helpdesk_pb2.HelpdeskAnalyticsSnapshot(
        window=snapshot.window.value,
        total_open_tickets=snapshot.total_open_tickets,
        queued_tickets_count=snapshot.queued_tickets_count,
        assigned_tickets_count=snapshot.assigned_tickets_count,
        escalated_tickets_count=snapshot.escalated_tickets_count,
        closed_tickets_count=snapshot.closed_tickets_count,
        period_created_tickets_count=snapshot.period_created_tickets_count,
        period_closed_tickets_count=snapshot.period_closed_tickets_count,
        feedback_count=snapshot.feedback_count,
        first_response_breach_count=snapshot.first_response_breach_count,
        resolution_breach_count=snapshot.resolution_breach_count,
    )
    if snapshot.average_first_response_time_seconds is not None:
        message.average_first_response_time_seconds = snapshot.average_first_response_time_seconds
    if snapshot.average_resolution_time_seconds is not None:
        message.average_resolution_time_seconds = snapshot.average_resolution_time_seconds
    if snapshot.satisfaction_average is not None:
        message.satisfaction_average = snapshot.satisfaction_average
    if snapshot.feedback_coverage_percent is not None:
        message.feedback_coverage_percent = snapshot.feedback_coverage_percent
    message.tickets_per_operator.extend(
        serialize_operator_ticket_load(item) for item in snapshot.tickets_per_operator
    )
    message.rating_distribution.extend(
        serialize_rating_bucket(item) for item in snapshot.rating_distribution
    )
    message.operator_snapshots.extend(
        serialize_operator_snapshot(item) for item in snapshot.operator_snapshots
    )
    message.category_snapshots.extend(
        serialize_category_snapshot(item) for item in snapshot.category_snapshots
    )
    message.best_operators_by_closures.extend(
        serialize_operator_snapshot(item) for item in snapshot.best_operators_by_closures
    )
    message.best_operators_by_satisfaction.extend(
        serialize_operator_snapshot(item) for item in snapshot.best_operators_by_satisfaction
    )
    message.top_categories.extend(
        serialize_category_snapshot(item) for item in snapshot.top_categories
    )
    message.sla_categories.extend(
        serialize_category_snapshot(item) for item in snapshot.sla_categories
    )
    return message


def deserialize_analytics_snapshot(
    snapshot: helpdesk_pb2.HelpdeskAnalyticsSnapshot,
) -> HelpdeskAnalyticsSnapshot:
    return HelpdeskAnalyticsSnapshot(
        window=AnalyticsWindow(snapshot.window),
        total_open_tickets=snapshot.total_open_tickets,
        queued_tickets_count=snapshot.queued_tickets_count,
        assigned_tickets_count=snapshot.assigned_tickets_count,
        escalated_tickets_count=snapshot.escalated_tickets_count,
        closed_tickets_count=snapshot.closed_tickets_count,
        tickets_per_operator=tuple(
            deserialize_operator_ticket_load(item) for item in snapshot.tickets_per_operator
        ),
        period_created_tickets_count=snapshot.period_created_tickets_count,
        period_closed_tickets_count=snapshot.period_closed_tickets_count,
        average_first_response_time_seconds=(
            snapshot.average_first_response_time_seconds
            if _has(snapshot, "average_first_response_time_seconds")
            else None
        ),
        average_resolution_time_seconds=(
            snapshot.average_resolution_time_seconds
            if _has(snapshot, "average_resolution_time_seconds")
            else None
        ),
        satisfaction_average=(
            snapshot.satisfaction_average if _has(snapshot, "satisfaction_average") else None
        ),
        feedback_count=snapshot.feedback_count,
        feedback_coverage_percent=(
            snapshot.feedback_coverage_percent
            if _has(snapshot, "feedback_coverage_percent")
            else None
        ),
        rating_distribution=tuple(
            deserialize_rating_bucket(item) for item in snapshot.rating_distribution
        ),
        operator_snapshots=tuple(
            deserialize_operator_snapshot(item) for item in snapshot.operator_snapshots
        ),
        category_snapshots=tuple(
            deserialize_category_snapshot(item) for item in snapshot.category_snapshots
        ),
        best_operators_by_closures=tuple(
            deserialize_operator_snapshot(item) for item in snapshot.best_operators_by_closures
        ),
        best_operators_by_satisfaction=tuple(
            deserialize_operator_snapshot(item) for item in snapshot.best_operators_by_satisfaction
        ),
        top_categories=tuple(
            deserialize_category_snapshot(item) for item in snapshot.top_categories
        ),
        first_response_breach_count=snapshot.first_response_breach_count,
        resolution_breach_count=snapshot.resolution_breach_count,
        sla_categories=tuple(
            deserialize_category_snapshot(item) for item in snapshot.sla_categories
        ),
    )


def serialize_operator_ticket_load(
    item: OperatorTicketLoad,
) -> helpdesk_pb2.OperatorTicketLoad:
    return helpdesk_pb2.OperatorTicketLoad(
        operator_id=item.operator_id,
        display_name=item.display_name,
        ticket_count=item.ticket_count,
    )


def deserialize_operator_ticket_load(
    item: helpdesk_pb2.OperatorTicketLoad,
) -> OperatorTicketLoad:
    return OperatorTicketLoad(
        operator_id=item.operator_id,
        display_name=item.display_name,
        ticket_count=item.ticket_count,
    )


def serialize_rating_bucket(
    item: AnalyticsRatingBucket,
) -> helpdesk_pb2.AnalyticsRatingBucket:
    return helpdesk_pb2.AnalyticsRatingBucket(rating=item.rating, count=item.count)


def deserialize_rating_bucket(
    item: helpdesk_pb2.AnalyticsRatingBucket,
) -> AnalyticsRatingBucket:
    return AnalyticsRatingBucket(rating=item.rating, count=item.count)


def serialize_operator_snapshot(
    item: AnalyticsOperatorSnapshot,
) -> helpdesk_pb2.AnalyticsOperatorSnapshot:
    message = helpdesk_pb2.AnalyticsOperatorSnapshot(
        operator_id=item.operator_id,
        display_name=item.display_name,
        active_ticket_count=item.active_ticket_count,
        closed_ticket_count=item.closed_ticket_count,
        feedback_count=item.feedback_count,
    )
    if item.average_first_response_time_seconds is not None:
        message.average_first_response_time_seconds = item.average_first_response_time_seconds
    if item.average_resolution_time_seconds is not None:
        message.average_resolution_time_seconds = item.average_resolution_time_seconds
    if item.average_satisfaction is not None:
        message.average_satisfaction = item.average_satisfaction
    return message


def deserialize_operator_snapshot(
    item: helpdesk_pb2.AnalyticsOperatorSnapshot,
) -> AnalyticsOperatorSnapshot:
    return AnalyticsOperatorSnapshot(
        operator_id=item.operator_id,
        display_name=item.display_name,
        active_ticket_count=item.active_ticket_count,
        closed_ticket_count=item.closed_ticket_count,
        average_first_response_time_seconds=(
            item.average_first_response_time_seconds
            if _has(item, "average_first_response_time_seconds")
            else None
        ),
        average_resolution_time_seconds=(
            item.average_resolution_time_seconds
            if _has(item, "average_resolution_time_seconds")
            else None
        ),
        average_satisfaction=(
            item.average_satisfaction if _has(item, "average_satisfaction") else None
        ),
        feedback_count=item.feedback_count,
    )


def serialize_category_snapshot(
    item: AnalyticsCategorySnapshot,
) -> helpdesk_pb2.AnalyticsCategorySnapshot:
    message = helpdesk_pb2.AnalyticsCategorySnapshot(
        category_title=item.category_title,
        created_ticket_count=item.created_ticket_count,
        open_ticket_count=item.open_ticket_count,
        closed_ticket_count=item.closed_ticket_count,
        feedback_count=item.feedback_count,
        sla_breach_count=item.sla_breach_count,
    )
    if item.category_id is not None:
        message.category_id = item.category_id
    if item.average_satisfaction is not None:
        message.average_satisfaction = item.average_satisfaction
    return message


def deserialize_category_snapshot(
    item: helpdesk_pb2.AnalyticsCategorySnapshot,
) -> AnalyticsCategorySnapshot:
    return AnalyticsCategorySnapshot(
        category_id=item.category_id if _has(item, "category_id") else None,
        category_title=item.category_title,
        created_ticket_count=item.created_ticket_count,
        open_ticket_count=item.open_ticket_count,
        closed_ticket_count=item.closed_ticket_count,
        average_satisfaction=(
            item.average_satisfaction if _has(item, "average_satisfaction") else None
        ),
        feedback_count=item.feedback_count,
        sla_breach_count=item.sla_breach_count,
    )


def _deserialize_attachment_summary(
    attachment: helpdesk_pb2.TicketAttachment,
) -> TicketAttachmentSummary:
    return TicketAttachmentSummary(
        kind=TicketAttachmentKind(attachment.kind),
        telegram_file_id=attachment.telegram_file_id,
        telegram_file_unique_id=(
            attachment.telegram_file_unique_id
            if _has(attachment, "telegram_file_unique_id")
            else None
        ),
        filename=attachment.filename if _has(attachment, "filename") else None,
        mime_type=attachment.mime_type if _has(attachment, "mime_type") else None,
        storage_path=attachment.storage_path if _has(attachment, "storage_path") else None,
    )


def _serialize_timestamp(value: datetime) -> Timestamp:
    message = Timestamp()
    message.FromDatetime(value.astimezone(UTC))
    return message


def _deserialize_timestamp(value: Timestamp) -> datetime:
    return cast(datetime, value.ToDatetime(tzinfo=UTC))


def _has(message: Any, field: str) -> bool:
    return bool(message.HasField(field))
