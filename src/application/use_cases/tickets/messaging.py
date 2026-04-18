from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import datetime
from uuid import UUID

from application.contracts.ai import (
    AIContextAttachment,
    AIServiceClientFactory,
    AnalyzedTicketSentimentResult,
    AnalyzeTicketSentimentCommand,
)
from application.contracts.tickets import AddInternalNoteCommand, OperatorTicketReplyCommand
from application.use_cases.tickets.common import (
    build_event_type_for_message,
    build_message_payload,
    build_ticket_summary,
    utcnow,
)
from application.use_cases.tickets.inbound_signals import (
    build_recent_ai_message_context,
    detect_duplicate_client_message,
    next_priority_for_sentiment,
    sentiment_severity,
)
from application.use_cases.tickets.summaries import OperatorReplyResult, TicketSummary
from domain.contracts.repositories import (
    OperatorRepository,
    TicketEventRepository,
    TicketInternalNoteRepository,
    TicketMessageRepository,
    TicketRepository,
)
from domain.entities.ticket import TicketAttachmentDetails, TicketMessageDetails
from domain.enums.tickets import (
    TicketEventType,
    TicketMessageSenderType,
    TicketSentiment,
    TicketSignalConfidence,
)
from domain.tickets import InvalidTicketTransitionError, ensure_operator_replyable

logger = logging.getLogger(__name__)


class AddMessageToTicketUseCase:
    def __init__(
        self,
        ticket_repository: TicketRepository,
        ticket_message_repository: TicketMessageRepository,
        ticket_event_repository: TicketEventRepository,
        ai_client_factory: AIServiceClientFactory | None = None,
    ) -> None:
        self.ticket_repository = ticket_repository
        self.ticket_message_repository = ticket_message_repository
        self.ticket_event_repository = ticket_event_repository
        self.ai_client_factory = ai_client_factory

    async def __call__(
        self,
        *,
        ticket_public_id: UUID,
        telegram_message_id: int,
        sender_type: TicketMessageSenderType,
        text: str | None,
        attachment: TicketAttachmentDetails | None = None,
        sender_operator_id: int | None = None,
        extra_event_payload: Mapping[str, object] | None = None,
    ) -> TicketSummary | None:
        ticket = await self.ticket_repository.get_by_public_id(ticket_public_id)
        if ticket is None or ticket.id is None:
            return None

        from domain.tickets import ensure_message_addable

        if text is None and attachment is None:
            raise ValueError("Нужно передать текст сообщения или вложение.")

        ensure_message_addable(ticket.status)
        current_time = utcnow()
        if sender_type == TicketMessageSenderType.OPERATOR and ticket.first_response_at is None:
            ticket.first_response_at = current_time
        ticket.updated_at = current_time

        message_sentiment: TicketSentiment | None = None
        message_sentiment_confidence: TicketSignalConfidence | None = None
        message_sentiment_reason: str | None = None
        extra_payload: dict[str, object] = dict(extra_event_payload or {})

        if sender_type == TicketMessageSenderType.CLIENT:
            recent_messages = tuple(
                await self.ticket_message_repository.list_recent_for_ticket(
                    ticket_id=ticket.id,
                    limit=6,
                )
            )
            duplicate_decision = detect_duplicate_client_message(
                recent_messages=recent_messages,
                incoming_text=text,
                incoming_attachment=attachment,
                current_time=current_time,
            )
            if duplicate_decision is not None:
                new_duplicate_count = duplicate_decision.canonical_message.duplicate_count + 1
                await self.ticket_message_repository.mark_duplicate(
                    ticket_id=ticket.id,
                    telegram_message_id=duplicate_decision.canonical_message.telegram_message_id,
                    occurred_at=current_time,
                )
                await self.ticket_event_repository.add(
                    ticket_id=ticket.id,
                    event_type=TicketEventType.CLIENT_MESSAGE_DUPLICATE_COLLAPSED,
                    payload_json={
                        "sender_type": TicketMessageSenderType.CLIENT.value,
                        "canonical_telegram_message_id": (
                            duplicate_decision.canonical_message.telegram_message_id
                        ),
                        "duplicate_telegram_message_id": telegram_message_id,
                        "duplicate_count": new_duplicate_count,
                        "reason_code": duplicate_decision.reason_code,
                    },
                )
                return build_ticket_summary(
                    ticket,
                    event_type=TicketEventType.CLIENT_MESSAGE_DUPLICATE_COLLAPSED,
                )

            sentiment_result = await self._analyze_client_sentiment(
                text=text,
                attachment=attachment,
                recent_messages=recent_messages,
            )
            if sentiment_result is not None and sentiment_result.available:
                message_sentiment = sentiment_result.sentiment
                message_sentiment_confidence = sentiment_result.confidence
                message_sentiment_reason = sentiment_result.reason
                extra_payload.update(
                    {
                        "sentiment": message_sentiment.value,
                        "sentiment_confidence": message_sentiment_confidence.value,
                    }
                )
                if message_sentiment_reason is not None:
                    extra_payload["sentiment_reason"] = message_sentiment_reason
                self._apply_ticket_sentiment(
                    ticket=ticket,
                    sentiment=message_sentiment,
                    confidence=message_sentiment_confidence,
                    reason=message_sentiment_reason,
                    detected_at=current_time,
                )
                bumped_priority = next_priority_for_sentiment(
                    current_priority=ticket.priority,
                    sentiment=message_sentiment,
                )
                if bumped_priority is not None and message_sentiment_confidence in {
                    TicketSignalConfidence.MEDIUM,
                    TicketSignalConfidence.HIGH,
                }:
                    previous_priority = ticket.priority
                    ticket.priority = bumped_priority
                    extra_payload["priority_bumped_from"] = previous_priority.value
                    extra_payload["priority_bumped_to"] = bumped_priority.value

        await self.ticket_message_repository.add(
            ticket_id=ticket.id,
            telegram_message_id=telegram_message_id,
            sender_type=sender_type,
            text=text,
            attachment=attachment,
            sender_operator_id=sender_operator_id,
            sentiment=message_sentiment,
            sentiment_confidence=message_sentiment_confidence,
            sentiment_reason=message_sentiment_reason,
        )

        event_type = build_event_type_for_message(sender_type)
        if event_type is not None:
            await self.ticket_event_repository.add(
                ticket_id=ticket.id,
                event_type=event_type,
                payload_json=build_message_payload(
                    telegram_message_id=telegram_message_id,
                    sender_type=sender_type,
                    sender_operator_id=sender_operator_id,
                    attachment=attachment,
                    extra_payload=extra_payload,
                ),
            )
        if (
            sender_type == TicketMessageSenderType.CLIENT
            and message_sentiment == TicketSentiment.ESCALATION_RISK
            and message_sentiment_confidence
            in {TicketSignalConfidence.MEDIUM, TicketSignalConfidence.HIGH}
        ):
            payload = {
                "sentiment": message_sentiment.value,
                "sentiment_confidence": message_sentiment_confidence.value,
                "telegram_message_id": telegram_message_id,
            }
            if message_sentiment_reason is not None:
                payload["sentiment_reason"] = message_sentiment_reason
            if "priority_bumped_to" in extra_payload:
                payload["priority_bumped_to"] = extra_payload["priority_bumped_to"]
                payload["priority_bumped_from"] = extra_payload["priority_bumped_from"]
            await self.ticket_event_repository.add(
                ticket_id=ticket.id,
                event_type=TicketEventType.CLIENT_SENTIMENT_FLAGGED,
                payload_json=payload,
            )

        return build_ticket_summary(ticket, event_type=event_type)

    async def _analyze_client_sentiment(
        self,
        *,
        text: str | None,
        attachment: TicketAttachmentDetails | None,
        recent_messages: tuple[TicketMessageDetails, ...],
    ) -> AnalyzedTicketSentimentResult | None:
        if self.ai_client_factory is None:
            return None
        try:
            async with self.ai_client_factory() as ai_client:
                return await ai_client.analyze_ticket_sentiment(
                    AnalyzeTicketSentimentCommand(
                        text=text,
                        recent_messages=build_recent_ai_message_context(
                            recent_messages=recent_messages
                        ),
                        attachment=(
                            None
                            if attachment is None
                            else AIContextAttachment(
                                kind=attachment.kind,
                                filename=attachment.filename,
                                mime_type=attachment.mime_type,
                            )
                        ),
                    )
                )
        except (PermissionError, RuntimeError, ValueError) as exc:
            logger.warning(
                "Ticket sentiment analysis skipped due to ai-service failure: %s",
                exc,
            )
            return None

    def _apply_ticket_sentiment(
        self,
        *,
        ticket: object,
        sentiment: TicketSentiment,
        confidence: TicketSignalConfidence,
        reason: str | None,
        detected_at: datetime,
    ) -> None:
        current_sentiment = getattr(ticket, "sentiment", None)
        if sentiment_severity(sentiment) < sentiment_severity(current_sentiment):
            return
        ticket.sentiment = sentiment
        ticket.sentiment_confidence = confidence
        ticket.sentiment_reason = reason
        ticket.sentiment_detected_at = detected_at


class ReplyToTicketAsOperatorUseCase:
    def __init__(
        self,
        ticket_repository: TicketRepository,
        ticket_message_repository: TicketMessageRepository,
        ticket_event_repository: TicketEventRepository,
        operator_repository: OperatorRepository,
    ) -> None:
        self.ticket_repository = ticket_repository
        self.operator_repository = operator_repository
        self._add_message_to_ticket = AddMessageToTicketUseCase(
            ticket_repository=ticket_repository,
            ticket_message_repository=ticket_message_repository,
            ticket_event_repository=ticket_event_repository,
            ai_client_factory=None,
        )

    async def __call__(
        self,
        command: OperatorTicketReplyCommand,
    ) -> OperatorReplyResult | None:
        ticket_details = await self.ticket_repository.get_details_by_public_id(
            command.ticket_public_id
        )
        if ticket_details is None:
            return None

        ensure_operator_replyable(ticket_details.status)

        operator_id = await self.operator_repository.get_or_create(
            telegram_user_id=command.operator.telegram_user_id,
            display_name=command.operator.display_name,
            username=command.operator.username,
        )
        if (
            ticket_details.assigned_operator_id is not None
            and ticket_details.assigned_operator_id != operator_id
        ):
            raise InvalidTicketTransitionError("С этой заявкой уже работает другой оператор.")

        ticket = await self._add_message_to_ticket(
            ticket_public_id=command.ticket_public_id,
            telegram_message_id=command.telegram_message_id,
            sender_type=TicketMessageSenderType.OPERATOR,
            text=command.text,
            attachment=command.attachment,
            sender_operator_id=operator_id,
        )
        if ticket is None:
            return None

        return OperatorReplyResult(
            ticket=ticket,
            client_chat_id=ticket_details.client_chat_id,
        )


class AddInternalNoteToTicketUseCase:
    def __init__(
        self,
        ticket_repository: TicketRepository,
        ticket_internal_note_repository: TicketInternalNoteRepository,
        operator_repository: OperatorRepository,
    ) -> None:
        self.ticket_repository = ticket_repository
        self.ticket_internal_note_repository = ticket_internal_note_repository
        self.operator_repository = operator_repository

    async def __call__(
        self,
        command: AddInternalNoteCommand,
    ) -> TicketSummary | None:
        normalized_text = command.text.strip()
        if not normalized_text:
            raise ValueError("Текст заметки не может быть пустым.")

        ticket = await self.ticket_repository.get_by_public_id(command.ticket_public_id)
        if ticket is None or ticket.id is None:
            return None

        operator_id = await self.operator_repository.get_or_create(
            telegram_user_id=command.author.telegram_user_id,
            display_name=command.author.display_name,
            username=command.author.username,
        )
        ticket.updated_at = utcnow()
        await self.ticket_internal_note_repository.add(
            ticket_id=ticket.id,
            author_operator_id=operator_id,
            text=normalized_text,
        )
        return build_ticket_summary(ticket)
