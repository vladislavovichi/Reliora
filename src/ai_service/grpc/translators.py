# mypy: disable-error-code="attr-defined,name-defined"
from __future__ import annotations

from datetime import UTC, datetime

from google.protobuf.timestamp_pb2 import Timestamp

from ai_service.grpc.generated import ai_service_pb2
from application.ai.summaries import AIPredictionConfidence
from application.contracts.ai import (
    AICategoryOption,
    AIContextAttachment,
    AIContextInternalNote,
    AIContextMessage,
    AIGeneratedTicketSummary,
    AIPredictedCategoryResult,
    AIPredictTicketCategoryCommand,
    AISuggestedMacro,
    GeneratedTicketSummaryResult,
    GenerateTicketSummaryCommand,
    SuggestedMacrosResult,
    SuggestMacrosCommand,
)
from domain.enums.tickets import TicketAttachmentKind, TicketMessageSenderType, TicketStatus


def serialize_timestamp(value: datetime) -> Timestamp:
    timestamp = Timestamp()
    timestamp.FromDatetime(value.astimezone(UTC))
    return timestamp


def deserialize_timestamp(value: Timestamp) -> datetime:
    return datetime.fromtimestamp(value.ToMilliseconds() / 1000, tz=UTC)


def serialize_attachment(
    attachment: AIContextAttachment | None,
) -> ai_service_pb2.AIContextAttachment | None:
    if attachment is None:
        return None
    message = ai_service_pb2.AIContextAttachment(kind=attachment.kind.value)
    if attachment.filename is not None:
        message.filename = attachment.filename
    if attachment.mime_type is not None:
        message.mime_type = attachment.mime_type
    return message


def deserialize_attachment(
    attachment: ai_service_pb2.AIContextAttachment | None,
) -> AIContextAttachment | None:
    if attachment is None:
        return None
    return AIContextAttachment(
        kind=TicketAttachmentKind(attachment.kind),
        filename=attachment.filename if attachment.HasField("filename") else None,
        mime_type=attachment.mime_type if attachment.HasField("mime_type") else None,
    )


def serialize_generate_ticket_summary_command(
    command: GenerateTicketSummaryCommand,
) -> ai_service_pb2.GenerateTicketSummaryCommand:
    message = ai_service_pb2.GenerateTicketSummaryCommand(
        ticket_public_id=str(command.ticket_public_id),
        subject=command.subject,
        status=command.status.value,
        tags=command.tags,
    )
    if command.category_title is not None:
        message.category_title = command.category_title
    message.message_history.extend(
        serialize_context_message(item) for item in command.message_history
    )
    message.internal_notes.extend(
        serialize_context_internal_note(item) for item in command.internal_notes
    )
    return message


def deserialize_generate_ticket_summary_command(
    command: ai_service_pb2.GenerateTicketSummaryCommand,
) -> GenerateTicketSummaryCommand:
    from uuid import UUID

    return GenerateTicketSummaryCommand(
        ticket_public_id=UUID(command.ticket_public_id),
        subject=command.subject,
        status=TicketStatus(command.status),
        category_title=command.category_title if command.HasField("category_title") else None,
        tags=tuple(command.tags),
        message_history=tuple(
            deserialize_context_message(item) for item in command.message_history
        ),
        internal_notes=tuple(
            deserialize_context_internal_note(item) for item in command.internal_notes
        ),
    )


def serialize_generated_ticket_summary_result(
    result: GeneratedTicketSummaryResult,
) -> ai_service_pb2.GenerateTicketSummaryResponse:
    message = ai_service_pb2.GenerateTicketSummaryResponse(available=result.available)
    if result.summary is not None:
        message.summary.CopyFrom(
            ai_service_pb2.GeneratedTicketSummary(
                short_summary=result.summary.short_summary,
                user_goal=result.summary.user_goal,
                actions_taken=result.summary.actions_taken,
                current_status=result.summary.current_status,
            )
        )
    if result.unavailable_reason is not None:
        message.unavailable_reason = result.unavailable_reason
    if result.model_id is not None:
        message.model_id = result.model_id
    return message


def deserialize_generated_ticket_summary_result(
    result: ai_service_pb2.GenerateTicketSummaryResponse,
) -> GeneratedTicketSummaryResult:
    summary = None
    if result.HasField("summary"):
        summary = AIGeneratedTicketSummary(
            short_summary=result.summary.short_summary,
            user_goal=result.summary.user_goal,
            actions_taken=result.summary.actions_taken,
            current_status=result.summary.current_status,
        )
    return GeneratedTicketSummaryResult(
        available=result.available,
        summary=summary,
        unavailable_reason=(
            result.unavailable_reason if result.HasField("unavailable_reason") else None
        ),
        model_id=result.model_id if result.HasField("model_id") else None,
    )


def serialize_suggest_macros_command(
    command: SuggestMacrosCommand,
) -> ai_service_pb2.SuggestMacrosCommand:
    message = ai_service_pb2.SuggestMacrosCommand(
        ticket_public_id=str(command.ticket_public_id),
        subject=command.subject,
        status=command.status.value,
        tags=command.tags,
    )
    if command.category_title is not None:
        message.category_title = command.category_title
    message.message_history.extend(
        serialize_context_message(item) for item in command.message_history
    )
    message.macros.extend(
        ai_service_pb2.MacroCandidate(id=item.id, title=item.title, body=item.body)
        for item in command.macros
    )
    return message


def deserialize_suggest_macros_command(
    command: ai_service_pb2.SuggestMacrosCommand,
) -> SuggestMacrosCommand:
    from uuid import UUID

    from application.contracts.ai import MacroCandidate

    return SuggestMacrosCommand(
        ticket_public_id=UUID(command.ticket_public_id),
        subject=command.subject,
        status=TicketStatus(command.status),
        category_title=command.category_title if command.HasField("category_title") else None,
        tags=tuple(command.tags),
        message_history=tuple(
            deserialize_context_message(item) for item in command.message_history
        ),
        macros=tuple(
            MacroCandidate(id=item.id, title=item.title, body=item.body) for item in command.macros
        ),
    )


def serialize_suggested_macros_result(
    result: SuggestedMacrosResult,
) -> ai_service_pb2.SuggestMacrosResponse:
    message = ai_service_pb2.SuggestMacrosResponse(available=result.available)
    message.suggestions.extend(
        ai_service_pb2.AISuggestedMacro(
            macro_id=item.macro_id,
            reason=item.reason,
            confidence=item.confidence.value,
        )
        for item in result.suggestions
    )
    if result.unavailable_reason is not None:
        message.unavailable_reason = result.unavailable_reason
    if result.model_id is not None:
        message.model_id = result.model_id
    return message


def deserialize_suggested_macros_result(
    result: ai_service_pb2.SuggestMacrosResponse,
) -> SuggestedMacrosResult:
    return SuggestedMacrosResult(
        available=result.available,
        suggestions=tuple(
            AISuggestedMacro(
                macro_id=item.macro_id,
                reason=item.reason,
                confidence=AIPredictionConfidence(item.confidence),
            )
            for item in result.suggestions
        ),
        unavailable_reason=(
            result.unavailable_reason if result.HasField("unavailable_reason") else None
        ),
        model_id=result.model_id if result.HasField("model_id") else None,
    )


def serialize_predict_category_command(
    command: AIPredictTicketCategoryCommand,
) -> ai_service_pb2.PredictCategoryCommand:
    message = ai_service_pb2.PredictCategoryCommand()
    if command.text is not None:
        message.text = command.text
    if command.attachment is not None:
        message.attachment.CopyFrom(serialize_attachment(command.attachment))
    message.categories.extend(
        ai_service_pb2.AICategoryOption(id=item.id, code=item.code, title=item.title)
        for item in command.categories
    )
    return message


def deserialize_predict_category_command(
    command: ai_service_pb2.PredictCategoryCommand,
) -> AIPredictTicketCategoryCommand:
    return AIPredictTicketCategoryCommand(
        text=command.text if command.HasField("text") else None,
        attachment=(
            deserialize_attachment(command.attachment) if command.HasField("attachment") else None
        ),
        categories=tuple(
            AICategoryOption(id=item.id, code=item.code, title=item.title)
            for item in command.categories
        ),
    )


def serialize_predicted_category_result(
    result: AIPredictedCategoryResult,
) -> ai_service_pb2.PredictCategoryResponse:
    message = ai_service_pb2.PredictCategoryResponse(
        available=result.available,
        confidence=result.confidence.value,
    )
    if result.category_id is not None:
        message.category_id = result.category_id
    if result.reason is not None:
        message.reason = result.reason
    if result.unavailable_reason is not None:
        message.unavailable_reason = result.unavailable_reason
    if result.model_id is not None:
        message.model_id = result.model_id
    return message


def deserialize_predicted_category_result(
    result: ai_service_pb2.PredictCategoryResponse,
) -> AIPredictedCategoryResult:
    return AIPredictedCategoryResult(
        available=result.available,
        category_id=result.category_id if result.HasField("category_id") else None,
        confidence=AIPredictionConfidence(result.confidence),
        reason=result.reason if result.HasField("reason") else None,
        unavailable_reason=(
            result.unavailable_reason if result.HasField("unavailable_reason") else None
        ),
        model_id=result.model_id if result.HasField("model_id") else None,
    )


def serialize_context_message(message: AIContextMessage) -> ai_service_pb2.AIContextMessage:
    result = ai_service_pb2.AIContextMessage(
        sender_type=message.sender_type.value,
        created_at=serialize_timestamp(message.created_at),
    )
    if message.sender_label is not None:
        result.sender_label = message.sender_label
    if message.text is not None:
        result.text = message.text
    if message.attachment is not None:
        result.attachment.CopyFrom(serialize_attachment(message.attachment))
    return result


def deserialize_context_message(message: ai_service_pb2.AIContextMessage) -> AIContextMessage:
    return AIContextMessage(
        sender_type=TicketMessageSenderType(message.sender_type),
        sender_label=message.sender_label if message.HasField("sender_label") else None,
        text=message.text if message.HasField("text") else None,
        created_at=deserialize_timestamp(message.created_at),
        attachment=(
            deserialize_attachment(message.attachment) if message.HasField("attachment") else None
        ),
    )


def serialize_context_internal_note(
    note: AIContextInternalNote,
) -> ai_service_pb2.AIContextInternalNote:
    result = ai_service_pb2.AIContextInternalNote(
        text=note.text,
        created_at=serialize_timestamp(note.created_at),
    )
    if note.author_name is not None:
        result.author_name = note.author_name
    return result


def deserialize_context_internal_note(
    note: ai_service_pb2.AIContextInternalNote,
) -> AIContextInternalNote:
    return AIContextInternalNote(
        author_name=note.author_name if note.HasField("author_name") else None,
        text=note.text,
        created_at=deserialize_timestamp(note.created_at),
    )
