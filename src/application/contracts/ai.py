from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from application.ai.summaries import AIPredictionConfidence
from domain.enums.tickets import TicketAttachmentKind, TicketMessageSenderType, TicketStatus


@dataclass(slots=True, frozen=True)
class PredictTicketCategoryCommand:
    text: str | None
    attachment_kind: TicketAttachmentKind | None = None
    attachment_filename: str | None = None
    attachment_mime_type: str | None = None


@dataclass(slots=True, frozen=True)
class AIContextAttachment:
    kind: TicketAttachmentKind
    filename: str | None = None
    mime_type: str | None = None


@dataclass(slots=True, frozen=True)
class AIContextMessage:
    sender_type: TicketMessageSenderType
    sender_label: str | None
    text: str | None
    created_at: datetime
    attachment: AIContextAttachment | None = None


@dataclass(slots=True, frozen=True)
class AIContextInternalNote:
    author_name: str | None
    text: str
    created_at: datetime


@dataclass(slots=True, frozen=True)
class GenerateTicketSummaryCommand:
    ticket_public_id: UUID
    subject: str
    status: TicketStatus
    category_title: str | None
    tags: tuple[str, ...] = ()
    message_history: tuple[AIContextMessage, ...] = ()
    internal_notes: tuple[AIContextInternalNote, ...] = ()


@dataclass(slots=True, frozen=True)
class AIGeneratedTicketSummary:
    short_summary: str
    user_goal: str
    actions_taken: str
    current_status: str


@dataclass(slots=True, frozen=True)
class GeneratedTicketSummaryResult:
    available: bool
    summary: AIGeneratedTicketSummary | None = None
    unavailable_reason: str | None = None
    model_id: str | None = None


@dataclass(slots=True, frozen=True)
class MacroCandidate:
    id: int
    title: str
    body: str


@dataclass(slots=True, frozen=True)
class SuggestMacrosCommand:
    ticket_public_id: UUID
    subject: str
    status: TicketStatus
    category_title: str | None
    tags: tuple[str, ...] = ()
    message_history: tuple[AIContextMessage, ...] = ()
    macros: tuple[MacroCandidate, ...] = ()


@dataclass(slots=True, frozen=True)
class AISuggestedMacro:
    macro_id: int
    reason: str
    confidence: AIPredictionConfidence = AIPredictionConfidence.MEDIUM


@dataclass(slots=True, frozen=True)
class SuggestedMacrosResult:
    available: bool
    suggestions: tuple[AISuggestedMacro, ...] = ()
    unavailable_reason: str | None = None
    model_id: str | None = None


@dataclass(slots=True, frozen=True)
class AICategoryOption:
    id: int
    code: str
    title: str


@dataclass(slots=True, frozen=True)
class AIPredictTicketCategoryCommand:
    text: str | None
    attachment: AIContextAttachment | None = None
    categories: tuple[AICategoryOption, ...] = ()


@dataclass(slots=True, frozen=True)
class AIPredictedCategoryResult:
    available: bool
    category_id: int | None = None
    confidence: AIPredictionConfidence = AIPredictionConfidence.NONE
    reason: str | None = None
    unavailable_reason: str | None = None
    model_id: str | None = None


class AIServiceClient(Protocol):
    async def get_service_status(self) -> tuple[str, str]: ...

    async def generate_ticket_summary(
        self,
        command: GenerateTicketSummaryCommand,
    ) -> GeneratedTicketSummaryResult: ...

    async def suggest_macros(
        self,
        command: SuggestMacrosCommand,
    ) -> SuggestedMacrosResult: ...

    async def predict_ticket_category(
        self,
        command: AIPredictTicketCategoryCommand,
    ) -> AIPredictedCategoryResult: ...


AIServiceClientFactory = Callable[
    [],
    AbstractAsyncContextManager[AIServiceClient],
]
