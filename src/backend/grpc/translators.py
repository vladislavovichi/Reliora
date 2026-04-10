from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from application.contracts.actors import OperatorIdentity, RequestActor
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
from application.use_cases.tickets.exports import TicketReportExport, TicketReportFormat
from application.use_cases.tickets.summaries import (
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
from backend.grpc.messages import (
    AnalyticsCategorySnapshotMessage,
    AnalyticsOperatorSnapshotMessage,
    AnalyticsRatingBucketMessage,
    ApplyMacroToTicketCommandMessage,
    AssignNextQueuedTicketCommandMessage,
    ClientTicketMessageCommandMessage,
    HelpdeskAnalyticsSnapshotMessage,
    MacroApplicationResultMessage,
    MacroSummaryMessage,
    OperatorIdentityMessage,
    OperatorReplyResultMessage,
    OperatorTicketLoadMessage,
    OperatorTicketReplyCommandMessage,
    OperatorTicketSummaryMessage,
    QueuedTicketSummaryMessage,
    RequestActorMessage,
    TicketAssignmentCommandMessage,
    TicketAttachmentMessage,
    TicketCategorySummaryMessage,
    TicketDetailsSummaryMessage,
    TicketInternalNoteSummaryMessage,
    TicketMessageSummaryMessage,
    TicketReportExportMessage,
    TicketSummaryMessage,
)
from domain.entities.ticket import TicketAttachmentDetails
from domain.enums.tickets import TicketAttachmentKind, TicketMessageSenderType, TicketStatus


def serialize_request_actor(actor: RequestActor | None) -> RequestActorMessage | None:
    if actor is None:
        return None
    return RequestActorMessage(telegram_user_id=actor.telegram_user_id)


def deserialize_request_actor(actor: RequestActorMessage | None) -> RequestActor | None:
    if actor is None:
        return None
    return RequestActor(telegram_user_id=actor.telegram_user_id)


def serialize_operator_identity(operator: OperatorIdentity) -> OperatorIdentityMessage:
    return OperatorIdentityMessage(
        telegram_user_id=operator.telegram_user_id,
        display_name=operator.display_name,
        username=operator.username,
    )


def deserialize_operator_identity(operator: OperatorIdentityMessage) -> OperatorIdentity:
    return OperatorIdentity(
        telegram_user_id=operator.telegram_user_id,
        display_name=operator.display_name,
        username=operator.username,
    )


def serialize_attachment(
    attachment: TicketAttachmentDetails | TicketAttachmentSummary | None,
) -> TicketAttachmentMessage | None:
    if attachment is None:
        return None
    return TicketAttachmentMessage(
        kind=attachment.kind.value,
        telegram_file_id=attachment.telegram_file_id,
        telegram_file_unique_id=attachment.telegram_file_unique_id,
        filename=attachment.filename,
        mime_type=attachment.mime_type,
        storage_path=attachment.storage_path,
    )


def deserialize_attachment(
    attachment: TicketAttachmentMessage | None,
) -> TicketAttachmentDetails | None:
    if attachment is None:
        return None
    return TicketAttachmentDetails(
        kind=TicketAttachmentKind(attachment.kind),
        telegram_file_id=attachment.telegram_file_id,
        telegram_file_unique_id=attachment.telegram_file_unique_id,
        filename=attachment.filename,
        mime_type=attachment.mime_type,
        storage_path=attachment.storage_path,
    )


def serialize_client_ticket_message_command(
    command: ClientTicketMessageCommand,
) -> ClientTicketMessageCommandMessage:
    return ClientTicketMessageCommandMessage(
        client_chat_id=command.client_chat_id,
        telegram_message_id=command.telegram_message_id,
        text=command.text,
        attachment=serialize_attachment(command.attachment),
        category_id=command.category_id,
    )


def deserialize_client_ticket_message_command(
    command: ClientTicketMessageCommandMessage,
) -> ClientTicketMessageCommand:
    return ClientTicketMessageCommand(
        client_chat_id=command.client_chat_id,
        telegram_message_id=command.telegram_message_id,
        text=command.text,
        attachment=deserialize_attachment(command.attachment),
        category_id=command.category_id,
    )


def serialize_operator_reply_command(
    command: OperatorTicketReplyCommand,
) -> OperatorTicketReplyCommandMessage:
    return OperatorTicketReplyCommandMessage(
        ticket_public_id=str(command.ticket_public_id),
        operator=serialize_operator_identity(command.operator),
        telegram_message_id=command.telegram_message_id,
        text=command.text,
        attachment=serialize_attachment(command.attachment),
    )


def deserialize_operator_reply_command(
    command: OperatorTicketReplyCommandMessage,
) -> OperatorTicketReplyCommand:
    return OperatorTicketReplyCommand(
        ticket_public_id=UUID(command.ticket_public_id),
        operator=deserialize_operator_identity(command.operator),
        telegram_message_id=command.telegram_message_id,
        text=command.text,
        attachment=deserialize_attachment(command.attachment),
    )


def serialize_ticket_assignment_command(
    command: TicketAssignmentCommand,
) -> TicketAssignmentCommandMessage:
    return TicketAssignmentCommandMessage(
        ticket_public_id=str(command.ticket_public_id),
        operator=serialize_operator_identity(command.operator),
    )


def deserialize_ticket_assignment_command(
    command: TicketAssignmentCommandMessage,
) -> TicketAssignmentCommand:
    return TicketAssignmentCommand(
        ticket_public_id=UUID(command.ticket_public_id),
        operator=deserialize_operator_identity(command.operator),
    )


def serialize_assign_next_command(
    command: AssignNextQueuedTicketCommand,
) -> AssignNextQueuedTicketCommandMessage:
    return AssignNextQueuedTicketCommandMessage(
        operator=serialize_operator_identity(command.operator),
        prioritize_priority=command.prioritize_priority,
    )


def deserialize_assign_next_command(
    command: AssignNextQueuedTicketCommandMessage,
) -> AssignNextQueuedTicketCommand:
    return AssignNextQueuedTicketCommand(
        operator=deserialize_operator_identity(command.operator),
        prioritize_priority=command.prioritize_priority,
    )


def serialize_apply_macro_command(
    command: ApplyMacroToTicketCommand,
) -> ApplyMacroToTicketCommandMessage:
    return ApplyMacroToTicketCommandMessage(
        ticket_public_id=str(command.ticket_public_id),
        macro_id=command.macro_id,
        operator=serialize_operator_identity(command.operator),
    )


def deserialize_apply_macro_command(
    command: ApplyMacroToTicketCommandMessage,
) -> ApplyMacroToTicketCommand:
    return ApplyMacroToTicketCommand(
        ticket_public_id=UUID(command.ticket_public_id),
        macro_id=command.macro_id,
        operator=deserialize_operator_identity(command.operator),
    )


def serialize_ticket_summary(ticket: TicketSummary) -> TicketSummaryMessage:
    return TicketSummaryMessage(
        public_id=str(ticket.public_id),
        public_number=ticket.public_number,
        status=ticket.status.value,
        created=ticket.created,
        event_type=ticket.event_type.value if ticket.event_type is not None else None,
    )


def deserialize_ticket_summary(ticket: TicketSummaryMessage) -> TicketSummary:
    from domain.enums.tickets import TicketEventType

    return TicketSummary(
        public_id=UUID(ticket.public_id),
        public_number=ticket.public_number,
        status=TicketStatus(ticket.status),
        created=ticket.created,
        event_type=TicketEventType(ticket.event_type) if ticket.event_type is not None else None,
    )


def serialize_queued_ticket(ticket: QueuedTicketSummary) -> QueuedTicketSummaryMessage:
    return QueuedTicketSummaryMessage(
        public_id=str(ticket.public_id),
        public_number=ticket.public_number,
        subject=ticket.subject,
        priority=ticket.priority,
        status=ticket.status.value,
        category_title=ticket.category_title,
    )


def deserialize_queued_ticket(ticket: QueuedTicketSummaryMessage) -> QueuedTicketSummary:
    return QueuedTicketSummary(
        public_id=UUID(ticket.public_id),
        public_number=ticket.public_number,
        subject=ticket.subject,
        priority=ticket.priority,
        status=TicketStatus(ticket.status),
        category_title=ticket.category_title,
    )


def serialize_operator_ticket(ticket: OperatorTicketSummary) -> OperatorTicketSummaryMessage:
    return OperatorTicketSummaryMessage(
        public_id=str(ticket.public_id),
        public_number=ticket.public_number,
        subject=ticket.subject,
        priority=ticket.priority,
        status=ticket.status.value,
        category_title=ticket.category_title,
    )


def deserialize_operator_ticket(ticket: OperatorTicketSummaryMessage) -> OperatorTicketSummary:
    return OperatorTicketSummary(
        public_id=UUID(ticket.public_id),
        public_number=ticket.public_number,
        subject=ticket.subject,
        priority=ticket.priority,
        status=TicketStatus(ticket.status),
        category_title=ticket.category_title,
    )


def serialize_category(category: TicketCategorySummary) -> TicketCategorySummaryMessage:
    return TicketCategorySummaryMessage(
        id=category.id,
        code=category.code,
        title=category.title,
        is_active=category.is_active,
        sort_order=category.sort_order,
    )


def deserialize_category(category: TicketCategorySummaryMessage) -> TicketCategorySummary:
    return TicketCategorySummary(
        id=category.id,
        code=category.code,
        title=category.title,
        is_active=category.is_active,
        sort_order=category.sort_order,
    )


def serialize_ticket_message(message: TicketMessageSummary) -> TicketMessageSummaryMessage:
    return TicketMessageSummaryMessage(
        sender_type=message.sender_type.value,
        sender_operator_id=message.sender_operator_id,
        sender_operator_name=message.sender_operator_name,
        text=message.text,
        created_at=message.created_at,
        attachment=serialize_attachment(message.attachment),
    )


def deserialize_ticket_message(message: TicketMessageSummaryMessage) -> TicketMessageSummary:
    return TicketMessageSummary(
        sender_type=TicketMessageSenderType(message.sender_type),
        sender_operator_id=message.sender_operator_id,
        sender_operator_name=message.sender_operator_name,
        text=message.text,
        created_at=message.created_at,
        attachment=(
            None
            if message.attachment is None
            else TicketAttachmentSummary(
                kind=TicketAttachmentKind(message.attachment.kind),
                telegram_file_id=message.attachment.telegram_file_id,
                telegram_file_unique_id=message.attachment.telegram_file_unique_id,
                filename=message.attachment.filename,
                mime_type=message.attachment.mime_type,
                storage_path=message.attachment.storage_path,
            )
        ),
    )


def serialize_ticket_note(note: TicketInternalNoteSummary) -> TicketInternalNoteSummaryMessage:
    return TicketInternalNoteSummaryMessage(
        id=note.id,
        author_operator_id=note.author_operator_id,
        author_operator_name=note.author_operator_name,
        text=note.text,
        created_at=note.created_at,
    )


def deserialize_ticket_note(note: TicketInternalNoteSummaryMessage) -> TicketInternalNoteSummary:
    return TicketInternalNoteSummary(
        id=note.id,
        author_operator_id=note.author_operator_id,
        author_operator_name=note.author_operator_name,
        text=note.text,
        created_at=note.created_at,
    )


def serialize_ticket_details(ticket: TicketDetailsSummary) -> TicketDetailsSummaryMessage:
    return TicketDetailsSummaryMessage(
        public_id=str(ticket.public_id),
        public_number=ticket.public_number,
        client_chat_id=ticket.client_chat_id,
        status=ticket.status.value,
        priority=ticket.priority,
        subject=ticket.subject,
        assigned_operator_id=ticket.assigned_operator_id,
        assigned_operator_name=ticket.assigned_operator_name,
        assigned_operator_telegram_user_id=ticket.assigned_operator_telegram_user_id,
        created_at=ticket.created_at,
        category_id=ticket.category_id,
        category_code=ticket.category_code,
        category_title=ticket.category_title,
        tags=ticket.tags,
        last_message_text=ticket.last_message_text,
        last_message_sender_type=(
            ticket.last_message_sender_type.value
            if ticket.last_message_sender_type is not None
            else None
        ),
        last_message_attachment=serialize_attachment(ticket.last_message_attachment),
        message_history=tuple(serialize_ticket_message(item) for item in ticket.message_history),
        internal_notes=tuple(serialize_ticket_note(item) for item in ticket.internal_notes),
    )


def deserialize_ticket_details(ticket: TicketDetailsSummaryMessage) -> TicketDetailsSummary:
    return TicketDetailsSummary(
        public_id=UUID(ticket.public_id),
        public_number=ticket.public_number,
        client_chat_id=ticket.client_chat_id,
        status=TicketStatus(ticket.status),
        priority=ticket.priority,
        subject=ticket.subject,
        assigned_operator_id=ticket.assigned_operator_id,
        assigned_operator_name=ticket.assigned_operator_name,
        assigned_operator_telegram_user_id=ticket.assigned_operator_telegram_user_id,
        created_at=ticket.created_at,
        category_id=ticket.category_id,
        category_code=ticket.category_code,
        category_title=ticket.category_title,
        tags=ticket.tags,
        last_message_text=ticket.last_message_text,
        last_message_sender_type=(
            TicketMessageSenderType(ticket.last_message_sender_type)
            if ticket.last_message_sender_type is not None
            else None
        ),
        last_message_attachment=(
            None
            if ticket.last_message_attachment is None
            else TicketAttachmentSummary(
                kind=TicketAttachmentKind(ticket.last_message_attachment.kind),
                telegram_file_id=ticket.last_message_attachment.telegram_file_id,
                telegram_file_unique_id=ticket.last_message_attachment.telegram_file_unique_id,
                filename=ticket.last_message_attachment.filename,
                mime_type=ticket.last_message_attachment.mime_type,
                storage_path=ticket.last_message_attachment.storage_path,
            )
        ),
        message_history=tuple(deserialize_ticket_message(item) for item in ticket.message_history),
        internal_notes=tuple(deserialize_ticket_note(item) for item in ticket.internal_notes),
    )


def serialize_operator_reply_result(result: OperatorReplyResult) -> OperatorReplyResultMessage:
    return OperatorReplyResultMessage(
        ticket=serialize_ticket_summary(result.ticket),
        client_chat_id=result.client_chat_id,
    )


def deserialize_operator_reply_result(result: OperatorReplyResultMessage) -> OperatorReplyResult:
    return OperatorReplyResult(
        ticket=deserialize_ticket_summary(result.ticket),
        client_chat_id=result.client_chat_id,
    )


def serialize_macro(macro: MacroSummary) -> MacroSummaryMessage:
    return MacroSummaryMessage(id=macro.id, title=macro.title, body=macro.body)


def deserialize_macro(macro: MacroSummaryMessage) -> MacroSummary:
    return MacroSummary(id=macro.id, title=macro.title, body=macro.body)


def serialize_macro_application_result(
    result: MacroApplicationResult,
) -> MacroApplicationResultMessage:
    return MacroApplicationResultMessage(
        ticket=serialize_ticket_summary(result.ticket),
        client_chat_id=result.client_chat_id,
        macro=serialize_macro(result.macro),
    )


def deserialize_macro_application_result(
    result: MacroApplicationResultMessage,
) -> MacroApplicationResult:
    return MacroApplicationResult(
        ticket=deserialize_ticket_summary(result.ticket),
        client_chat_id=result.client_chat_id,
        macro=deserialize_macro(result.macro),
    )


def serialize_export(export: TicketReportExport) -> TicketReportExportMessage:
    return TicketReportExportMessage(
        format=export.format.value,
        filename=export.filename,
        content_type=export.content_type,
        content=export.content,
        report_public_number=export.report.public_number,
    )


def deserialize_export(export: TicketReportExportMessage) -> TicketReportExport:
    from application.use_cases.tickets.exports import TicketReport
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


def serialize_operator_ticket_load(load: OperatorTicketLoad) -> OperatorTicketLoadMessage:
    return OperatorTicketLoadMessage(
        operator_id=load.operator_id,
        display_name=load.display_name,
        ticket_count=load.ticket_count,
    )


def deserialize_operator_ticket_load(load: OperatorTicketLoadMessage) -> OperatorTicketLoad:
    return OperatorTicketLoad(
        operator_id=load.operator_id,
        display_name=load.display_name,
        ticket_count=load.ticket_count,
    )


def serialize_rating_bucket(bucket: AnalyticsRatingBucket) -> AnalyticsRatingBucketMessage:
    return AnalyticsRatingBucketMessage(rating=bucket.rating, count=bucket.count)


def deserialize_rating_bucket(bucket: AnalyticsRatingBucketMessage) -> AnalyticsRatingBucket:
    return AnalyticsRatingBucket(rating=bucket.rating, count=bucket.count)


def serialize_operator_snapshot(
    snapshot: AnalyticsOperatorSnapshot,
) -> AnalyticsOperatorSnapshotMessage:
    return AnalyticsOperatorSnapshotMessage(
        operator_id=snapshot.operator_id,
        display_name=snapshot.display_name,
        active_ticket_count=snapshot.active_ticket_count,
        closed_ticket_count=snapshot.closed_ticket_count,
        average_first_response_time_seconds=snapshot.average_first_response_time_seconds,
        average_resolution_time_seconds=snapshot.average_resolution_time_seconds,
        average_satisfaction=snapshot.average_satisfaction,
        feedback_count=snapshot.feedback_count,
    )


def deserialize_operator_snapshot(
    snapshot: AnalyticsOperatorSnapshotMessage,
) -> AnalyticsOperatorSnapshot:
    return AnalyticsOperatorSnapshot(
        operator_id=snapshot.operator_id,
        display_name=snapshot.display_name,
        active_ticket_count=snapshot.active_ticket_count,
        closed_ticket_count=snapshot.closed_ticket_count,
        average_first_response_time_seconds=snapshot.average_first_response_time_seconds,
        average_resolution_time_seconds=snapshot.average_resolution_time_seconds,
        average_satisfaction=snapshot.average_satisfaction,
        feedback_count=snapshot.feedback_count,
    )


def serialize_category_snapshot(
    snapshot: AnalyticsCategorySnapshot,
) -> AnalyticsCategorySnapshotMessage:
    return AnalyticsCategorySnapshotMessage(
        category_id=snapshot.category_id,
        category_title=snapshot.category_title,
        created_ticket_count=snapshot.created_ticket_count,
        open_ticket_count=snapshot.open_ticket_count,
        closed_ticket_count=snapshot.closed_ticket_count,
        average_satisfaction=snapshot.average_satisfaction,
        feedback_count=snapshot.feedback_count,
        sla_breach_count=snapshot.sla_breach_count,
    )


def deserialize_category_snapshot(
    snapshot: AnalyticsCategorySnapshotMessage,
) -> AnalyticsCategorySnapshot:
    return AnalyticsCategorySnapshot(
        category_id=snapshot.category_id,
        category_title=snapshot.category_title,
        created_ticket_count=snapshot.created_ticket_count,
        open_ticket_count=snapshot.open_ticket_count,
        closed_ticket_count=snapshot.closed_ticket_count,
        average_satisfaction=snapshot.average_satisfaction,
        feedback_count=snapshot.feedback_count,
        sla_breach_count=snapshot.sla_breach_count,
    )


def serialize_analytics_snapshot(
    snapshot: HelpdeskAnalyticsSnapshot,
) -> HelpdeskAnalyticsSnapshotMessage:
    return HelpdeskAnalyticsSnapshotMessage(
        window=snapshot.window.value,
        total_open_tickets=snapshot.total_open_tickets,
        queued_tickets_count=snapshot.queued_tickets_count,
        assigned_tickets_count=snapshot.assigned_tickets_count,
        escalated_tickets_count=snapshot.escalated_tickets_count,
        closed_tickets_count=snapshot.closed_tickets_count,
        tickets_per_operator=tuple(
            serialize_operator_ticket_load(item) for item in snapshot.tickets_per_operator
        ),
        period_created_tickets_count=snapshot.period_created_tickets_count,
        period_closed_tickets_count=snapshot.period_closed_tickets_count,
        average_first_response_time_seconds=snapshot.average_first_response_time_seconds,
        average_resolution_time_seconds=snapshot.average_resolution_time_seconds,
        satisfaction_average=snapshot.satisfaction_average,
        feedback_count=snapshot.feedback_count,
        feedback_coverage_percent=snapshot.feedback_coverage_percent,
        rating_distribution=tuple(
            serialize_rating_bucket(item) for item in snapshot.rating_distribution
        ),
        operator_snapshots=tuple(
            serialize_operator_snapshot(item) for item in snapshot.operator_snapshots
        ),
        category_snapshots=tuple(
            serialize_category_snapshot(item) for item in snapshot.category_snapshots
        ),
        best_operators_by_closures=tuple(
            serialize_operator_snapshot(item) for item in snapshot.best_operators_by_closures
        ),
        best_operators_by_satisfaction=tuple(
            serialize_operator_snapshot(item) for item in snapshot.best_operators_by_satisfaction
        ),
        top_categories=tuple(serialize_category_snapshot(item) for item in snapshot.top_categories),
        first_response_breach_count=snapshot.first_response_breach_count,
        resolution_breach_count=snapshot.resolution_breach_count,
        sla_categories=tuple(serialize_category_snapshot(item) for item in snapshot.sla_categories),
    )


def deserialize_analytics_snapshot(
    snapshot: HelpdeskAnalyticsSnapshotMessage,
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
        average_first_response_time_seconds=snapshot.average_first_response_time_seconds,
        average_resolution_time_seconds=snapshot.average_resolution_time_seconds,
        satisfaction_average=snapshot.satisfaction_average,
        feedback_count=snapshot.feedback_count,
        feedback_coverage_percent=snapshot.feedback_coverage_percent,
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
