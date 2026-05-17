from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager
from typing import Protocol
from uuid import UUID

from application.ai.summaries import (
    TicketAssistSnapshot,
    TicketCategoryPrediction,
    TicketReplyDraft,
)
from application.contracts.actors import OperatorIdentity, RequestActor
from application.contracts.ai import PredictTicketCategoryCommand
from application.contracts.tickets import (
    AddInternalNoteCommand,
    ApplyMacroToTicketCommand,
    AssignNextQueuedTicketCommand,
    ClientTicketMessageCommand,
    OperatorTicketReplyCommand,
    TicketAssignmentCommand,
)
from application.services.stats import AnalyticsWindow, HelpdeskAnalyticsSnapshot
from application.use_cases.analytics.exports import (
    AnalyticsExportFormat,
    AnalyticsSection,
    AnalyticsSnapshotExport,
)
from application.use_cases.tickets.exports import TicketReportExport, TicketReportFormat
from application.use_cases.tickets.operator_invites import (
    OperatorInviteCodePreview,
    OperatorInviteCodeRedemptionResult,
    OperatorInviteCodeSummary,
)
from application.use_cases.tickets.summaries import (
    AccessContextSummary,
    HistoricalTicketSummary,
    MacroApplicationResult,
    MacroSummary,
    OperatorReplyResult,
    OperatorRoleMutationResult,
    OperatorSummary,
    OperatorTicketSummary,
    QueuedTicketSummary,
    TagSummary,
    TicketCategorySummary,
    TicketDetailsSummary,
    TicketFeedbackMutationResult,
    TicketFeedbackSummary,
    TicketSummary,
    TicketTagMutationResult,
    TicketTagsSummary,
)


class HelpdeskBackendClient(Protocol):
    async def get_backend_status(self) -> tuple[str, str]: ...

    async def get_access_context(
        self,
        *,
        actor: RequestActor,
    ) -> AccessContextSummary: ...

    async def get_client_active_ticket(self, *, client_chat_id: int) -> TicketSummary | None: ...

    async def list_client_ticket_categories(self) -> Sequence[TicketCategorySummary]: ...

    async def create_ticket_from_client_message(
        self,
        command: ClientTicketMessageCommand,
    ) -> TicketSummary: ...

    async def create_ticket_from_client_intake(
        self,
        command: ClientTicketMessageCommand,
    ) -> TicketSummary: ...

    async def get_ticket_details(
        self,
        *,
        ticket_public_id: UUID,
        actor: RequestActor | None = None,
    ) -> TicketDetailsSummary | None: ...

    async def list_queued_tickets(
        self,
        *,
        actor: RequestActor | None = None,
    ) -> Sequence[QueuedTicketSummary]: ...

    async def list_operator_tickets(
        self,
        *,
        operator_telegram_user_id: int,
        actor: RequestActor | None = None,
    ) -> Sequence[OperatorTicketSummary]: ...

    async def list_archived_tickets(
        self,
        *,
        actor: RequestActor | None = None,
    ) -> Sequence[HistoricalTicketSummary]: ...

    async def assign_next_ticket_to_operator(
        self,
        command: AssignNextQueuedTicketCommand,
        actor: RequestActor | None = None,
    ) -> TicketSummary | None: ...

    async def assign_ticket_to_operator(
        self,
        command: TicketAssignmentCommand,
        actor: RequestActor | None = None,
    ) -> TicketSummary | None: ...

    async def close_ticket(
        self,
        *,
        ticket_public_id: UUID,
        actor: RequestActor | None = None,
    ) -> TicketSummary | None: ...

    async def close_ticket_as_operator(
        self,
        *,
        ticket_public_id: UUID,
        actor: RequestActor | None,
    ) -> TicketSummary | None: ...

    async def close_ticket_as_client(
        self,
        *,
        ticket_public_id: UUID,
        actor: RequestActor | None,
    ) -> TicketSummary | None: ...

    async def escalate_ticket_as_operator(
        self,
        *,
        ticket_public_id: UUID,
        actor: RequestActor | None,
    ) -> TicketSummary | None: ...

    async def reply_to_ticket_as_operator(
        self,
        command: OperatorTicketReplyCommand,
        actor: RequestActor | None = None,
    ) -> OperatorReplyResult | None: ...

    async def add_internal_note_to_ticket(
        self,
        command: AddInternalNoteCommand,
        actor: RequestActor | None = None,
    ) -> TicketSummary | None: ...

    async def list_operators(
        self,
        *,
        actor: RequestActor | None = None,
    ) -> Sequence[OperatorSummary]: ...

    async def create_operator_invite(
        self,
        *,
        actor: RequestActor | None = None,
    ) -> OperatorInviteCodeSummary: ...

    async def preview_operator_invite(
        self,
        *,
        code: str,
    ) -> OperatorInviteCodePreview: ...

    async def redeem_operator_invite(
        self,
        *,
        code: str,
        operator: OperatorIdentity,
    ) -> OperatorInviteCodeRedemptionResult: ...

    async def promote_operator(
        self,
        operator: OperatorIdentity,
        actor: RequestActor | None = None,
    ) -> OperatorRoleMutationResult: ...

    async def revoke_operator(
        self,
        *,
        telegram_user_id: int,
        actor: RequestActor | None = None,
    ) -> OperatorRoleMutationResult | None: ...

    async def list_macros(
        self,
        *,
        actor: RequestActor | None = None,
    ) -> Sequence[MacroSummary]: ...

    async def get_macro(
        self,
        *,
        macro_id: int,
        actor: RequestActor | None = None,
    ) -> MacroSummary | None: ...

    async def create_macro(
        self,
        *,
        title: str,
        body: str,
        actor: RequestActor | None = None,
    ) -> MacroSummary: ...

    async def update_macro_title(
        self,
        *,
        macro_id: int,
        title: str,
        actor: RequestActor | None = None,
    ) -> MacroSummary | None: ...

    async def update_macro_body(
        self,
        *,
        macro_id: int,
        body: str,
        actor: RequestActor | None = None,
    ) -> MacroSummary | None: ...

    async def delete_macro(
        self,
        *,
        macro_id: int,
        actor: RequestActor | None = None,
    ) -> MacroSummary | None: ...

    async def list_ticket_categories(
        self,
        *,
        actor: RequestActor | None = None,
    ) -> Sequence[TicketCategorySummary]: ...

    async def get_ticket_category(
        self,
        *,
        category_id: int,
        actor: RequestActor | None = None,
    ) -> TicketCategorySummary | None: ...

    async def create_ticket_category(
        self,
        *,
        title: str,
        actor: RequestActor | None = None,
    ) -> TicketCategorySummary: ...

    async def update_ticket_category_title(
        self,
        *,
        category_id: int,
        title: str,
        actor: RequestActor | None = None,
    ) -> TicketCategorySummary | None: ...

    async def set_ticket_category_active(
        self,
        *,
        category_id: int,
        is_active: bool,
        actor: RequestActor | None = None,
    ) -> TicketCategorySummary | None: ...

    async def list_ticket_tags(
        self,
        *,
        ticket_public_id: UUID,
        actor: RequestActor | None = None,
    ) -> TicketTagsSummary | None: ...

    async def list_available_tags(
        self,
        *,
        actor: RequestActor | None = None,
    ) -> Sequence[TagSummary]: ...

    async def add_tag_to_ticket(
        self,
        *,
        ticket_public_id: UUID,
        tag_name: str,
        actor: RequestActor | None = None,
    ) -> TicketTagMutationResult | None: ...

    async def remove_tag_from_ticket(
        self,
        *,
        ticket_public_id: UUID,
        tag_name: str,
        actor: RequestActor | None = None,
    ) -> TicketTagMutationResult | None: ...

    async def submit_ticket_feedback_rating(
        self,
        *,
        ticket_public_id: UUID,
        client_chat_id: int,
        rating: int,
    ) -> TicketFeedbackMutationResult: ...

    async def get_ticket_feedback(
        self,
        *,
        ticket_public_id: UUID,
    ) -> TicketFeedbackSummary | None: ...

    async def add_ticket_feedback_comment(
        self,
        *,
        ticket_public_id: UUID,
        client_chat_id: int,
        comment: str,
    ) -> TicketFeedbackMutationResult: ...

    async def apply_macro_to_ticket(
        self,
        command: ApplyMacroToTicketCommand,
        actor: RequestActor | None = None,
    ) -> MacroApplicationResult | None: ...

    async def get_ticket_ai_assist_snapshot(
        self,
        *,
        ticket_public_id: UUID,
        refresh_summary: bool = False,
        actor: RequestActor | None = None,
    ) -> TicketAssistSnapshot | None: ...

    async def generate_ticket_reply_draft(
        self,
        *,
        ticket_public_id: UUID,
        actor: RequestActor | None = None,
    ) -> TicketReplyDraft | None: ...

    async def predict_ticket_category(
        self,
        command: PredictTicketCategoryCommand,
        *,
        actor: RequestActor | None = None,
    ) -> TicketCategoryPrediction: ...

    async def export_ticket_report(
        self,
        *,
        ticket_public_id: UUID,
        format: TicketReportFormat,
        actor: RequestActor | None = None,
    ) -> TicketReportExport | None: ...

    async def get_analytics_snapshot(
        self,
        *,
        window: AnalyticsWindow,
        actor: RequestActor | None = None,
    ) -> HelpdeskAnalyticsSnapshot: ...

    async def export_analytics_snapshot(
        self,
        *,
        window: AnalyticsWindow,
        section: AnalyticsSection,
        format: AnalyticsExportFormat,
        actor: RequestActor | None = None,
    ) -> AnalyticsSnapshotExport: ...


HelpdeskBackendClientFactory = Callable[
    [],
    AbstractAsyncContextManager[HelpdeskBackendClient],
]
