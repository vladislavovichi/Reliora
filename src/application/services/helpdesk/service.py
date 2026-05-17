from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from application.ai.summaries import (
    TicketAssistSnapshot,
    TicketCategoryPrediction,
    TicketReplyDraft,
)
from application.contracts.actors import OperatorIdentity, RequestActor
from application.contracts.ai import AIServiceClientFactory, PredictTicketCategoryCommand
from application.contracts.runtime import CorrelationIdProvider, SLADeadlineScheduler
from application.contracts.tickets import (
    AddInternalNoteCommand,
    AssignNextQueuedTicketCommand,
    ApplyMacroToTicketCommand,
    ClientTicketMessageCommand,
    OperatorTicketReplyCommand,
    TicketAssignmentCommand,
)
from application.errors import InternalApplicationError
from application.services.audit import AuditTrail
from application.services.helpdesk._context import _HelpdeskContext
from application.services.helpdesk.ai_operations import HelpdeskAIOperations
from application.services.helpdesk.catalog_operations import HelpdeskCatalogOperations
from application.services.helpdesk.components import (
    HelpdeskComponents,
    HelpdeskExportRenderers,
    HelpdeskRepositoryBundle,
    build_helpdesk_component_dependencies,
    build_helpdesk_components,
)
from application.services.helpdesk.operator_operations import HelpdeskOperatorOperations
from application.services.helpdesk.sla_operations import HelpdeskSLAOperations
from application.services.helpdesk.ticket_operations import HelpdeskTicketOperations
from application.services.stats import (
    AnalyticsWindow,
    HelpdeskAnalyticsSnapshot,
    HelpdeskOperationalStats,
)
from application.use_cases.ai.settings import AISettingsProvider, InMemoryAISettingsRepository
from application.use_cases.analytics.exports import (
    AnalyticsExportFormat,
    AnalyticsSection,
    AnalyticsSnapshotExport,
)
from application.use_cases.tickets.exports import (
    TicketReportExport,
    TicketReportFormat,
)
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
    SLAAutoReassignmentTarget,
    SLABatchProcessingResult,
    TagSummary,
    TicketCategorySummary,
    TicketDetailsSummary,
    TicketFeedbackMutationResult,
    TicketFeedbackSummary,
    TicketSLAEvaluationSummary,
    TicketStats,
    TicketSummary,
    TicketTagMutationResult,
    TicketTagsSummary,
)
from domain.entities.ticket import TicketAttachmentDetails
from domain.enums.tickets import TicketMessageSenderType

HelpdeskServiceFactory = Callable[[], AbstractAsyncContextManager["HelpdeskService"]]


@dataclass
class HelpdeskService:
    repository_bundle: HelpdeskRepositoryBundle
    ai_client_factory: AIServiceClientFactory
    export_renderers: HelpdeskExportRenderers
    super_admin_telegram_user_ids: frozenset[int]
    include_internal_notes_in_ticket_reports: bool = True
    ai_settings_provider: AISettingsProvider = field(default_factory=InMemoryAISettingsRepository)
    sla_deadline_scheduler: SLADeadlineScheduler | None = None
    correlation_id_provider: CorrelationIdProvider | None = None
    _components: HelpdeskComponents = field(init=False, repr=False)
    _audit: AuditTrail = field(init=False, repr=False)
    _ticket_ops: HelpdeskTicketOperations = field(init=False, repr=False)
    _catalog_ops: HelpdeskCatalogOperations = field(init=False, repr=False)
    _operator_ops: HelpdeskOperatorOperations = field(init=False, repr=False)
    _sla_ops: HelpdeskSLAOperations = field(init=False, repr=False)
    _ai_ops: HelpdeskAIOperations = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._components = self._build_components()
        self._validate_configuration()
        self._audit = self._build_audit_trail()
        self._build_handlers()

    def _validate_configuration(self) -> None:
        if not self.super_admin_telegram_user_ids:
            raise InternalApplicationError("Не настроены Telegram user id супер администраторов.")

    def _build_audit_trail(self) -> AuditTrail:
        return AuditTrail(
            repository=self.repository_bundle.audit_log,
            correlation_id_provider=self.correlation_id_provider,
        )

    def _build_components(self) -> HelpdeskComponents:
        return build_helpdesk_components(
            build_helpdesk_component_dependencies(
                self.repository_bundle,
                ai_client_factory=self.ai_client_factory,
                super_admin_telegram_user_ids=self.super_admin_telegram_user_ids,
                export_renderers=self.export_renderers,
                include_internal_notes_in_ticket_reports=(
                    self.include_internal_notes_in_ticket_reports
                ),
                ai_settings_provider=self.ai_settings_provider,
            )
        )

    def _build_ctx(self) -> _HelpdeskContext:
        return _HelpdeskContext(
            components=self._components,
            audit=self._audit,
            sla_deadline_scheduler=self.sla_deadline_scheduler,
        )

    def _build_handlers(self) -> None:
        ctx = self._build_ctx()
        self._ticket_ops = HelpdeskTicketOperations(ctx)
        self._catalog_ops = HelpdeskCatalogOperations(ctx)
        self._operator_ops = HelpdeskOperatorOperations(ctx)
        self._sla_ops = HelpdeskSLAOperations(ctx)
        self._ai_ops = HelpdeskAIOperations(ctx)

    # -------------------------------------------------------------------------
    # Ticket operations
    # -------------------------------------------------------------------------

    async def create_ticket_from_client_message(
        self,
        command: ClientTicketMessageCommand,
    ) -> TicketSummary:
        return await self._ticket_ops.create_ticket_from_client_message(command)

    async def create_ticket_from_client_intake(
        self,
        command: ClientTicketMessageCommand,
    ) -> TicketSummary:
        return await self._ticket_ops.create_ticket_from_client_intake(command)

    async def get_client_active_ticket(self, *, client_chat_id: int) -> TicketSummary | None:
        return await self._ticket_ops.get_client_active_ticket(client_chat_id=client_chat_id)

    async def get_ticket_feedback(
        self,
        *,
        ticket_public_id: UUID,
    ) -> TicketFeedbackSummary | None:
        return await self._ticket_ops.get_ticket_feedback(ticket_public_id=ticket_public_id)

    async def submit_ticket_feedback_rating(
        self,
        *,
        ticket_public_id: UUID,
        client_chat_id: int,
        rating: int,
    ) -> TicketFeedbackMutationResult:
        return await self._ticket_ops.submit_ticket_feedback_rating(
            ticket_public_id=ticket_public_id,
            client_chat_id=client_chat_id,
            rating=rating,
        )

    async def add_ticket_feedback_comment(
        self,
        *,
        ticket_public_id: UUID,
        client_chat_id: int,
        comment: str,
    ) -> TicketFeedbackMutationResult:
        return await self._ticket_ops.add_ticket_feedback_comment(
            ticket_public_id=ticket_public_id,
            client_chat_id=client_chat_id,
            comment=comment,
        )

    async def list_client_ticket_categories(self) -> Sequence[TicketCategorySummary]:
        return await self._ticket_ops.list_client_ticket_categories()

    async def add_message_to_ticket(
        self,
        *,
        ticket_public_id: UUID,
        telegram_message_id: int,
        sender_type: TicketMessageSenderType,
        text: str | None,
        attachment: TicketAttachmentDetails | None = None,
        sender_operator_id: int | None = None,
    ) -> TicketSummary | None:
        return await self._ticket_ops.add_message_to_ticket(
            ticket_public_id=ticket_public_id,
            telegram_message_id=telegram_message_id,
            sender_type=sender_type,
            text=text,
            attachment=attachment,
            sender_operator_id=sender_operator_id,
        )

    async def assign_ticket_to_operator(
        self,
        command: TicketAssignmentCommand,
        actor: RequestActor | None = None,
    ) -> TicketSummary | None:
        return await self._ticket_ops.assign_ticket_to_operator(command, actor)

    async def close_ticket(
        self,
        *,
        ticket_public_id: UUID,
        actor: RequestActor | None = None,
    ) -> TicketSummary | None:
        return await self._ticket_ops.close_ticket(
            ticket_public_id=ticket_public_id,
            actor=actor,
        )

    async def close_ticket_as_operator(
        self,
        *,
        ticket_public_id: UUID,
        actor: RequestActor | None,
    ) -> TicketSummary | None:
        return await self._ticket_ops.close_ticket_as_operator(
            ticket_public_id=ticket_public_id,
            actor=actor,
        )

    async def get_next_queued_ticket(
        self,
        *,
        prioritize_priority: bool = False,
    ) -> QueuedTicketSummary | None:
        return await self._ticket_ops.get_next_queued_ticket(
            prioritize_priority=prioritize_priority,
        )

    async def list_queued_tickets(
        self,
        *,
        limit: int | None = None,
        prioritize_priority: bool = False,
        actor: RequestActor | None = None,
    ) -> Sequence[QueuedTicketSummary]:
        return await self._ticket_ops.list_queued_tickets(
            limit=limit,
            prioritize_priority=prioritize_priority,
            actor=actor,
        )

    async def assign_next_ticket_to_operator(
        self,
        command: AssignNextQueuedTicketCommand,
        actor: RequestActor | None = None,
    ) -> TicketSummary | None:
        return await self._ticket_ops.assign_next_ticket_to_operator(command, actor)

    async def list_operator_tickets(
        self,
        *,
        operator_telegram_user_id: int,
        limit: int | None = None,
        actor: RequestActor | None = None,
    ) -> Sequence[OperatorTicketSummary]:
        return await self._ticket_ops.list_operator_tickets(
            operator_telegram_user_id=operator_telegram_user_id,
            limit=limit,
            actor=actor,
        )

    async def list_archived_tickets(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
        actor: RequestActor | None = None,
    ) -> Sequence[HistoricalTicketSummary]:
        return await self._ticket_ops.list_archived_tickets(
            limit=limit,
            offset=offset,
            actor=actor,
        )

    async def get_ticket_details(
        self,
        *,
        ticket_public_id: UUID,
        actor: RequestActor | None = None,
    ) -> TicketDetailsSummary | None:
        return await self._ticket_ops.get_ticket_details(
            ticket_public_id=ticket_public_id,
            actor=actor,
        )

    async def export_ticket_report(
        self,
        *,
        ticket_public_id: UUID,
        format: TicketReportFormat,
        actor: RequestActor | None = None,
    ) -> TicketReportExport | None:
        return await self._ticket_ops.export_ticket_report(
            ticket_public_id=ticket_public_id,
            format=format,
            actor=actor,
        )

    async def reply_to_ticket_as_operator(
        self,
        command: OperatorTicketReplyCommand,
        actor: RequestActor | None = None,
    ) -> OperatorReplyResult | None:
        return await self._ticket_ops.reply_to_ticket_as_operator(command, actor)

    async def add_internal_note_to_ticket(
        self,
        command: AddInternalNoteCommand,
        actor: RequestActor | None = None,
    ) -> TicketSummary | None:
        return await self._ticket_ops.add_internal_note_to_ticket(command, actor)

    async def escalate_ticket(
        self,
        *,
        ticket_public_id: UUID,
        actor: RequestActor | None = None,
    ) -> TicketSummary | None:
        return await self._ticket_ops.escalate_ticket(
            ticket_public_id=ticket_public_id,
            actor=actor,
        )

    async def escalate_ticket_as_operator(
        self,
        *,
        ticket_public_id: UUID,
        actor: RequestActor | None,
    ) -> TicketSummary | None:
        return await self._ticket_ops.escalate_ticket_as_operator(
            ticket_public_id=ticket_public_id,
            actor=actor,
        )

    async def get_basic_stats(self) -> TicketStats:
        return await self._ticket_ops.get_basic_stats()

    # -------------------------------------------------------------------------
    # Catalog operations
    # -------------------------------------------------------------------------

    async def list_ticket_categories(
        self,
        *,
        actor: RequestActor | None = None,
    ) -> Sequence[TicketCategorySummary]:
        return await self._catalog_ops.list_ticket_categories(actor=actor)

    async def get_ticket_category(
        self,
        *,
        category_id: int,
        actor: RequestActor | None = None,
    ) -> TicketCategorySummary | None:
        return await self._catalog_ops.get_ticket_category(category_id=category_id, actor=actor)

    async def create_ticket_category(
        self,
        *,
        title: str,
        actor: RequestActor | None = None,
    ) -> TicketCategorySummary:
        return await self._catalog_ops.create_ticket_category(title=title, actor=actor)

    async def update_ticket_category_title(
        self,
        *,
        category_id: int,
        title: str,
        actor: RequestActor | None = None,
    ) -> TicketCategorySummary | None:
        return await self._catalog_ops.update_ticket_category_title(
            category_id=category_id,
            title=title,
            actor=actor,
        )

    async def set_ticket_category_active(
        self,
        *,
        category_id: int,
        is_active: bool,
        actor: RequestActor | None = None,
    ) -> TicketCategorySummary | None:
        return await self._catalog_ops.set_ticket_category_active(
            category_id=category_id,
            is_active=is_active,
            actor=actor,
        )

    async def list_macros(
        self,
        *,
        actor: RequestActor | None = None,
    ) -> Sequence[MacroSummary]:
        return await self._catalog_ops.list_macros(actor=actor)

    async def get_macro(
        self,
        *,
        macro_id: int,
        actor: RequestActor | None = None,
    ) -> MacroSummary | None:
        return await self._catalog_ops.get_macro(macro_id=macro_id, actor=actor)

    async def create_macro(
        self,
        *,
        title: str,
        body: str,
        actor: RequestActor | None = None,
    ) -> MacroSummary:
        return await self._catalog_ops.create_macro(title=title, body=body, actor=actor)

    async def update_macro_title(
        self,
        *,
        macro_id: int,
        title: str,
        actor: RequestActor | None = None,
    ) -> MacroSummary | None:
        return await self._catalog_ops.update_macro_title(
            macro_id=macro_id,
            title=title,
            actor=actor,
        )

    async def update_macro_body(
        self,
        *,
        macro_id: int,
        body: str,
        actor: RequestActor | None = None,
    ) -> MacroSummary | None:
        return await self._catalog_ops.update_macro_body(
            macro_id=macro_id,
            body=body,
            actor=actor,
        )

    async def delete_macro(
        self,
        *,
        macro_id: int,
        actor: RequestActor | None = None,
    ) -> MacroSummary | None:
        return await self._catalog_ops.delete_macro(macro_id=macro_id, actor=actor)

    async def apply_macro_to_ticket(
        self,
        command: ApplyMacroToTicketCommand,
        actor: RequestActor | None = None,
    ) -> MacroApplicationResult | None:
        return await self._catalog_ops.apply_macro_to_ticket(command, actor)

    async def list_ticket_tags(
        self,
        *,
        ticket_public_id: UUID,
        actor: RequestActor | None = None,
    ) -> TicketTagsSummary | None:
        return await self._catalog_ops.list_ticket_tags(
            ticket_public_id=ticket_public_id,
            actor=actor,
        )

    async def list_available_tags(
        self,
        *,
        actor: RequestActor | None = None,
    ) -> Sequence[TagSummary]:
        return await self._catalog_ops.list_available_tags(actor=actor)

    async def add_tag_to_ticket(
        self,
        *,
        ticket_public_id: UUID,
        tag_name: str,
        actor: RequestActor | None = None,
    ) -> TicketTagMutationResult | None:
        return await self._catalog_ops.add_tag_to_ticket(
            ticket_public_id=ticket_public_id,
            tag_name=tag_name,
            actor=actor,
        )

    async def remove_tag_from_ticket(
        self,
        *,
        ticket_public_id: UUID,
        tag_name: str,
        actor: RequestActor | None = None,
    ) -> TicketTagMutationResult | None:
        return await self._catalog_ops.remove_tag_from_ticket(
            ticket_public_id=ticket_public_id,
            tag_name=tag_name,
            actor=actor,
        )

    # -------------------------------------------------------------------------
    # Operator operations
    # -------------------------------------------------------------------------

    async def list_operators(
        self,
        *,
        actor: RequestActor | None = None,
    ) -> Sequence[OperatorSummary]:
        return await self._operator_ops.list_operators(actor=actor)

    async def get_access_context(
        self,
        *,
        actor: RequestActor | None,
    ) -> AccessContextSummary:
        return await self._operator_ops.get_access_context(actor=actor)

    async def promote_operator(
        self,
        operator: OperatorIdentity,
        actor: RequestActor | None = None,
    ) -> OperatorRoleMutationResult:
        return await self._operator_ops.promote_operator(operator, actor)

    async def revoke_operator(
        self,
        *,
        telegram_user_id: int,
        actor: RequestActor | None = None,
    ) -> OperatorRoleMutationResult | None:
        return await self._operator_ops.revoke_operator(
            telegram_user_id=telegram_user_id,
            actor=actor,
        )

    async def create_operator_invite(
        self,
        *,
        actor: RequestActor | None = None,
    ) -> OperatorInviteCodeSummary:
        return await self._operator_ops.create_operator_invite(actor=actor)

    async def preview_operator_invite(
        self,
        *,
        code: str,
    ) -> OperatorInviteCodePreview:
        return await self._operator_ops.preview_operator_invite(code=code)

    async def redeem_operator_invite(
        self,
        *,
        code: str,
        operator: OperatorIdentity,
    ) -> OperatorInviteCodeRedemptionResult:
        return await self._operator_ops.redeem_operator_invite(code=code, operator=operator)

    async def get_operational_stats(
        self,
        *,
        actor: RequestActor | None = None,
    ) -> HelpdeskOperationalStats:
        return await self._operator_ops.get_operational_stats(actor=actor)

    async def get_analytics_snapshot(
        self,
        *,
        window: AnalyticsWindow,
        actor: RequestActor | None = None,
    ) -> HelpdeskAnalyticsSnapshot:
        return await self._operator_ops.get_analytics_snapshot(window=window, actor=actor)

    async def export_analytics_snapshot(
        self,
        *,
        window: AnalyticsWindow,
        section: AnalyticsSection,
        format: AnalyticsExportFormat,
        actor: RequestActor | None = None,
    ) -> AnalyticsSnapshotExport:
        return await self._operator_ops.export_analytics_snapshot(
            window=window,
            section=section,
            format=format,
            actor=actor,
        )

    # -------------------------------------------------------------------------
    # SLA operations
    # -------------------------------------------------------------------------

    async def evaluate_ticket_sla_state(
        self,
        *,
        ticket_public_id: UUID,
        now: datetime | None = None,
    ) -> TicketSLAEvaluationSummary | None:
        return await self._sla_ops.evaluate_ticket_sla_state(
            ticket_public_id=ticket_public_id,
            now=now,
        )

    async def auto_escalate_ticket_by_sla(
        self,
        *,
        ticket_public_id: UUID,
        now: datetime | None = None,
    ) -> TicketSummary | None:
        return await self._sla_ops.auto_escalate_ticket_by_sla(
            ticket_public_id=ticket_public_id,
            now=now,
        )

    async def auto_reassign_ticket_by_sla(
        self,
        *,
        ticket_public_id: UUID,
        telegram_user_id: int,
        display_name: str,
        username: str | None = None,
        now: datetime | None = None,
    ) -> TicketSummary | None:
        return await self._sla_ops.auto_reassign_ticket_by_sla(
            ticket_public_id=ticket_public_id,
            telegram_user_id=telegram_user_id,
            display_name=display_name,
            username=username,
            now=now,
        )

    async def run_ticket_sla_checks(
        self,
        *,
        now: datetime | None = None,
        limit: int | None = None,
        reassignment_targets: Sequence[SLAAutoReassignmentTarget] = (),
    ) -> SLABatchProcessingResult:
        return await self._sla_ops.run_ticket_sla_checks(
            now=now,
            limit=limit,
            reassignment_targets=reassignment_targets,
        )

    # -------------------------------------------------------------------------
    # AI operations
    # -------------------------------------------------------------------------

    async def get_ticket_ai_assist_snapshot(
        self,
        *,
        ticket_public_id: UUID,
        refresh_summary: bool = False,
        actor: RequestActor | None = None,
    ) -> TicketAssistSnapshot | None:
        return await self._ai_ops.get_ticket_ai_assist_snapshot(
            ticket_public_id=ticket_public_id,
            refresh_summary=refresh_summary,
            actor=actor,
        )

    async def predict_ticket_category(
        self,
        command: PredictTicketCategoryCommand,
        *,
        actor: RequestActor | None = None,
    ) -> TicketCategoryPrediction:
        return await self._ai_ops.predict_ticket_category(command, actor=actor)

    async def generate_ticket_reply_draft(
        self,
        *,
        ticket_public_id: UUID,
        actor: RequestActor | None = None,
    ) -> TicketReplyDraft | None:
        return await self._ai_ops.generate_ticket_reply_draft(
            ticket_public_id=ticket_public_id,
            actor=actor,
        )
