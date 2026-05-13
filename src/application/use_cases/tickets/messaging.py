from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from application.contracts.ai import (
    AIContextAttachment,
    AIServiceClientFactory,
    AnalyzedTicketSentimentResult,
    AnalyzeTicketSentimentCommand,
)
from application.contracts.tickets import AddInternalNoteCommand, OperatorTicketReplyCommand
from application.errors import InternalApplicationError, ValidationAppError
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
from domain.entities.ticket import Ticket as TicketEntity
from domain.entities.ticket import TicketAttachmentDetails, TicketMessageDetails
from domain.enums.tickets import (
    TicketEventType,
    TicketMessageSenderType,
    TicketSentiment,
    TicketSignalConfidence,
)
from domain.tickets import InvalidTicketTransitionError, ensure_operator_replyable

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _MessageEffects:
    sentiment: TicketSentiment | None = None
    sentiment_confidence: TicketSignalConfidence | None = None
    sentiment_reason: str | None = None
    extra_payload: dict[str, object] | None = None

    def __post_init__(self) -> None:
        if self.extra_payload is None:
            self.extra_payload = {}


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
        ticket: TicketEntity | None = None,
    ) -> TicketSummary | None:
        if ticket is None:
            ticket = await self.ticket_repository.get_by_public_id(ticket_public_id)
        if ticket is None:
            return None
        if ticket.public_id != ticket_public_id:
            raise InternalApplicationError("Передана заявка с другим публичным идентификатором.")
        ticket_id = self._require_ticket_id(ticket)

        self._validate_message_transition(ticket=ticket, text=text, attachment=attachment)
        current_time = utcnow()
        self._apply_message_timestamp_side_effects(
            ticket=ticket,
            sender_type=sender_type,
            current_time=current_time,
        )
        effects = _MessageEffects(extra_payload=dict(extra_event_payload or {}))

        if sender_type == TicketMessageSenderType.CLIENT:
            recent_messages = tuple(
                await self.ticket_message_repository.list_recent_for_ticket(
                    ticket_id=ticket_id,
                    limit=6,
                )
            )
            duplicate_result = await self._collapse_duplicate_client_message(
                ticket=ticket,
                telegram_message_id=telegram_message_id,
                text=text,
                attachment=attachment,
                recent_messages=recent_messages,
                current_time=current_time,
            )
            if duplicate_result is not None:
                await self.ticket_repository.update(ticket)
                return duplicate_result

            await self._apply_client_sentiment_side_effects(
                ticket=ticket,
                effects=effects,
                recent_messages=recent_messages,
                text=text,
                attachment=attachment,
                current_time=current_time,
            )

        await self.ticket_repository.update(ticket)
        event_type = await self._persist_message_and_event(
            ticket=ticket,
            telegram_message_id=telegram_message_id,
            sender_type=sender_type,
            text=text,
            attachment=attachment,
            sender_operator_id=sender_operator_id,
            effects=effects,
        )
        await self._record_notification_and_audit_side_effects(
            ticket=ticket,
            telegram_message_id=telegram_message_id,
            sender_type=sender_type,
            effects=effects,
        )
        return build_ticket_summary(ticket, event_type=event_type)

    def _require_ticket_id(self, ticket: TicketEntity) -> int:
        if ticket.id is None:
            raise InternalApplicationError("Не удалось определить внутренний идентификатор заявки.")
        return ticket.id

    def _require_extra_payload(self, effects: _MessageEffects) -> dict[str, object]:
        if effects.extra_payload is None:
            raise InternalApplicationError("Не удалось подготовить метаданные события заявки.")
        return effects.extra_payload

    def _validate_message_transition(
        self,
        *,
        ticket: TicketEntity,
        text: str | None,
        attachment: TicketAttachmentDetails | None,
    ) -> None:
        from domain.tickets import ensure_message_addable

        if text is None and attachment is None:
            raise ValidationAppError("Нужно передать текст сообщения или вложение.")
        ensure_message_addable(ticket.status)

    def _apply_message_timestamp_side_effects(
        self,
        *,
        ticket: TicketEntity,
        sender_type: TicketMessageSenderType,
        current_time: datetime,
    ) -> None:
        if sender_type == TicketMessageSenderType.OPERATOR and ticket.first_response_at is None:
            ticket.first_response_at = current_time
        ticket.updated_at = current_time

    async def _collapse_duplicate_client_message(
        self,
        *,
        ticket: TicketEntity,
        telegram_message_id: int,
        text: str | None,
        attachment: TicketAttachmentDetails | None,
        recent_messages: tuple[TicketMessageDetails, ...],
        current_time: datetime,
    ) -> TicketSummary | None:
        ticket_id = self._require_ticket_id(ticket)
        duplicate_decision = detect_duplicate_client_message(
            recent_messages=recent_messages,
            incoming_text=text,
            incoming_attachment=attachment,
            current_time=current_time,
        )
        if duplicate_decision is None:
            return None

        new_duplicate_count = duplicate_decision.canonical_message.duplicate_count + 1
        await self.ticket_message_repository.mark_duplicate(
            ticket_id=ticket_id,
            telegram_message_id=duplicate_decision.canonical_message.telegram_message_id,
            occurred_at=current_time,
        )
        await self.ticket_event_repository.add(
            ticket_id=ticket_id,
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

    async def _apply_client_sentiment_side_effects(
        self,
        *,
        ticket: TicketEntity,
        effects: _MessageEffects,
        recent_messages: tuple[TicketMessageDetails, ...],
        text: str | None,
        attachment: TicketAttachmentDetails | None,
        current_time: datetime,
    ) -> None:
        sentiment_result = await self._analyze_client_sentiment(
            text=text,
            attachment=attachment,
            recent_messages=recent_messages,
        )
        if sentiment_result is None or not sentiment_result.available:
            return

        effects.sentiment = sentiment_result.sentiment
        effects.sentiment_confidence = sentiment_result.confidence
        effects.sentiment_reason = sentiment_result.reason
        extra_payload = self._require_extra_payload(effects)
        extra_payload.update(
            {
                "sentiment": effects.sentiment.value,
                "sentiment_confidence": effects.sentiment_confidence.value,
            }
        )
        if effects.sentiment_reason is not None:
            extra_payload["sentiment_reason"] = effects.sentiment_reason
        self._apply_ticket_sentiment(
            ticket=ticket,
            sentiment=effects.sentiment,
            confidence=effects.sentiment_confidence,
            reason=effects.sentiment_reason,
            detected_at=current_time,
        )
        self._apply_priority_bump(ticket=ticket, effects=effects)

    def _apply_priority_bump(
        self,
        *,
        ticket: TicketEntity,
        effects: _MessageEffects,
    ) -> None:
        if effects.sentiment is None:
            return
        bumped_priority = next_priority_for_sentiment(
            current_priority=ticket.priority,
            sentiment=effects.sentiment,
        )
        if bumped_priority is None or effects.sentiment_confidence not in {
            TicketSignalConfidence.MEDIUM,
            TicketSignalConfidence.HIGH,
        }:
            return
        previous_priority = ticket.priority
        ticket.priority = bumped_priority
        extra_payload = self._require_extra_payload(effects)
        extra_payload["priority_bumped_from"] = previous_priority.value
        extra_payload["priority_bumped_to"] = bumped_priority.value

    async def _persist_message_and_event(
        self,
        *,
        ticket: TicketEntity,
        telegram_message_id: int,
        sender_type: TicketMessageSenderType,
        text: str | None,
        attachment: TicketAttachmentDetails | None,
        sender_operator_id: int | None,
        effects: _MessageEffects,
    ) -> TicketEventType | None:
        ticket_id = self._require_ticket_id(ticket)
        await self.ticket_message_repository.add(
            ticket_id=ticket_id,
            telegram_message_id=telegram_message_id,
            sender_type=sender_type,
            text=text,
            attachment=attachment,
            sender_operator_id=sender_operator_id,
            sentiment=effects.sentiment,
            sentiment_confidence=effects.sentiment_confidence,
            sentiment_reason=effects.sentiment_reason,
        )
        event_type = build_event_type_for_message(sender_type)
        if event_type is not None:
            await self.ticket_event_repository.add(
                ticket_id=ticket_id,
                event_type=event_type,
                payload_json=build_message_payload(
                    telegram_message_id=telegram_message_id,
                    sender_type=sender_type,
                    sender_operator_id=sender_operator_id,
                    attachment=attachment,
                    extra_payload=effects.extra_payload,
                ),
            )
        return event_type

    async def _record_notification_and_audit_side_effects(
        self,
        *,
        ticket: TicketEntity,
        telegram_message_id: int,
        sender_type: TicketMessageSenderType,
        effects: _MessageEffects,
    ) -> None:
        ticket_id = self._require_ticket_id(ticket)
        extra_payload = effects.extra_payload or {}
        message_sentiment = effects.sentiment
        message_sentiment_confidence = effects.sentiment_confidence
        message_sentiment_reason = effects.sentiment_reason
        if (
            sender_type == TicketMessageSenderType.CLIENT
            and message_sentiment == TicketSentiment.ESCALATION_RISK
            and message_sentiment_confidence
            in {TicketSignalConfidence.MEDIUM, TicketSignalConfidence.HIGH}
        ):
            payload: dict[str, object] = {
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
                ticket_id=ticket_id,
                event_type=TicketEventType.CLIENT_SENTIMENT_FLAGGED,
                payload_json=payload,
            )

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
        ticket: TicketEntity,
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
        operator_repository: OperatorRepository,
        add_message_to_ticket: AddMessageToTicketUseCase,
    ) -> None:
        self.ticket_repository = ticket_repository
        self.operator_repository = operator_repository
        self._add_message_to_ticket = add_message_to_ticket

    async def __call__(
        self,
        command: OperatorTicketReplyCommand,
    ) -> OperatorReplyResult | None:
        ticket = await self.ticket_repository.get_by_public_id(command.ticket_public_id)
        if ticket is None or ticket.id is None:
            return None

        ensure_operator_replyable(ticket.status)

        operator_id = await self.operator_repository.get_or_create(
            telegram_user_id=command.operator.telegram_user_id,
            display_name=command.operator.display_name,
            username=command.operator.username,
        )
        if ticket.assigned_operator_id is not None and ticket.assigned_operator_id != operator_id:
            raise InvalidTicketTransitionError("С этой заявкой уже работает другой оператор.")

        ticket_summary = await self._add_message_to_ticket(
            ticket_public_id=command.ticket_public_id,
            telegram_message_id=command.telegram_message_id,
            sender_type=TicketMessageSenderType.OPERATOR,
            text=command.text,
            attachment=command.attachment,
            sender_operator_id=operator_id,
            ticket=ticket,
        )
        if ticket_summary is None:
            return None

        return OperatorReplyResult(
            ticket=ticket_summary,
            client_chat_id=ticket.client_chat_id,
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
            raise ValidationAppError("Текст заметки не может быть пустым.")

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
