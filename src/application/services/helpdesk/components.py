from dataclasses import dataclass

from application.contracts.ai import AIServiceClientFactory
from application.services.helpdesk.permissions import HelpdeskPermissionGuard
from application.services.stats import HelpdeskStatsService
from application.use_cases.ai.assist import (
    BuildTicketAssistSnapshotUseCase,
    GenerateTicketReplyDraftUseCase,
    PredictTicketCategoryUseCase,
)
from application.use_cases.ai.settings import (
    AISettingsProvider,
    InMemoryAISettingsRepository,
)
from application.use_cases.analytics.exports import (
    AnalyticsSnapshotRenderer,
    ExportAnalyticsSnapshotUseCase,
)
from application.use_cases.tickets.categories import (
    CreateTicketCategoryUseCase,
    GetTicketCategoryUseCase,
    ListTicketCategoriesUseCase,
    SetTicketCategoryActiveUseCase,
    UpdateTicketCategoryTitleUseCase,
)
from application.use_cases.tickets.creation import (
    CreateTicketFromClientMessageUseCase,
    GetActiveClientTicketUseCase,
)
from application.use_cases.tickets.exports import ExportTicketReportUseCase, TicketReportRenderer
from application.use_cases.tickets.feedback import (
    AddTicketFeedbackCommentUseCase,
    GetTicketFeedbackUseCase,
    SubmitTicketFeedbackRatingUseCase,
)
from application.use_cases.tickets.macros import (
    ApplyMacroToTicketUseCase,
    CreateMacroUseCase,
    DeleteMacroUseCase,
    GetMacroUseCase,
    ListMacrosUseCase,
    UpdateMacroBodyUseCase,
    UpdateMacroTitleUseCase,
)
from application.use_cases.tickets.messaging import (
    AddInternalNoteToTicketUseCase,
    AddMessageToTicketUseCase,
    ReplyToTicketAsOperatorUseCase,
)
from application.use_cases.tickets.operator_invites import (
    CreateOperatorInviteCodeUseCase,
    PreviewOperatorInviteCodeUseCase,
    RedeemOperatorInviteCodeUseCase,
)
from application.use_cases.tickets.operators import (
    ListOperatorsUseCase,
    PromoteOperatorUseCase,
    RevokeOperatorUseCase,
)
from application.use_cases.tickets.queue import (
    AssignNextQueuedTicketUseCase,
    AssignTicketToOperatorUseCase,
    GetNextQueuedTicketUseCase,
    GetTicketDetailsUseCase,
    ListArchivedTicketsUseCase,
    ListOperatorTicketsUseCase,
    ListQueuedTicketsUseCase,
)
from application.use_cases.tickets.sla import (
    AutoEscalateTicketBySLAUseCase,
    AutoReassignTicketBySLAUseCase,
    EvaluateTicketSLAStateUseCase,
    RunTicketSLAChecksUseCase,
)
from application.use_cases.tickets.tags import (
    AddTagToTicketUseCase,
    ListAvailableTagsUseCase,
    ListTicketTagsUseCase,
    RemoveTagFromTicketUseCase,
)
from application.use_cases.tickets.workflow import (
    BasicStatsUseCase,
    CloseTicketUseCase,
    EscalateTicketUseCase,
)
from domain.contracts.repositories import (
    AuditLogRepository,
    MacroRepository,
    OperatorInviteCodeRepository,
    OperatorRepository,
    SLAPolicyRepository,
    TagRepository,
    TicketAISummaryRepository,
    TicketAnalyticsRepository,
    TicketCategoryRepository,
    TicketEventRepository,
    TicketFeedbackRepository,
    TicketInternalNoteRepository,
    TicketMessageRepository,
    TicketRepository,
    TicketTagRepository,
)


@dataclass(slots=True, frozen=True)
class HelpdeskRepositoryBundle:
    ticket: TicketRepository
    ticket_analytics: TicketAnalyticsRepository
    ticket_feedback: TicketFeedbackRepository
    ticket_ai_summary: TicketAISummaryRepository
    ticket_message: TicketMessageRepository
    ticket_internal_note: TicketInternalNoteRepository
    ticket_event: TicketEventRepository
    ticket_tag: TicketTagRepository
    audit_log: AuditLogRepository
    operator: OperatorRepository
    operator_invite: OperatorInviteCodeRepository
    macro: MacroRepository
    sla_policy: SLAPolicyRepository
    tag: TagRepository
    ticket_category: TicketCategoryRepository


@dataclass(slots=True, frozen=True)
class HelpdeskExportRenderers:
    ticket_report_csv: TicketReportRenderer
    ticket_report_html: TicketReportRenderer
    analytics_snapshot_csv: AnalyticsSnapshotRenderer
    analytics_snapshot_html: AnalyticsSnapshotRenderer


@dataclass(slots=True, frozen=True)
class HelpdeskTicketDependencies:
    ticket_repository: TicketRepository
    ticket_analytics_repository: TicketAnalyticsRepository
    ticket_feedback_repository: TicketFeedbackRepository
    ticket_ai_summary_repository: TicketAISummaryRepository
    ticket_message_repository: TicketMessageRepository
    ticket_internal_note_repository: TicketInternalNoteRepository
    ticket_event_repository: TicketEventRepository
    ticket_tag_repository: TicketTagRepository


@dataclass(slots=True, frozen=True)
class HelpdeskCatalogDependencies:
    macro_repository: MacroRepository
    tag_repository: TagRepository
    ticket_category_repository: TicketCategoryRepository


@dataclass(slots=True, frozen=True)
class HelpdeskOperatorDependencies:
    operator_repository: OperatorRepository
    operator_invite_repository: OperatorInviteCodeRepository
    super_admin_telegram_user_ids: frozenset[int]


@dataclass(slots=True, frozen=True)
class HelpdeskSLADependencies:
    sla_policy_repository: SLAPolicyRepository


@dataclass(slots=True, frozen=True)
class HelpdeskAIDependencies:
    ai_client_factory: AIServiceClientFactory
    ai_settings_provider: AISettingsProvider


@dataclass(slots=True, frozen=True)
class HelpdeskFeedbackAuditStatsDependencies:
    export_renderers: HelpdeskExportRenderers
    include_internal_notes_in_ticket_reports: bool = True


@dataclass(slots=True, frozen=True)
class HelpdeskComponentDependencies:
    tickets: HelpdeskTicketDependencies
    catalog: HelpdeskCatalogDependencies
    operators: HelpdeskOperatorDependencies
    sla: HelpdeskSLADependencies
    ai: HelpdeskAIDependencies
    feedback_audit_stats: HelpdeskFeedbackAuditStatsDependencies


def _deps_from_bundle(
    bundle: HelpdeskRepositoryBundle,
    *,
    super_admin_telegram_user_ids: frozenset[int],
    ai_client_factory: AIServiceClientFactory,
    export_renderers: HelpdeskExportRenderers,
    include_internal_notes_in_ticket_reports: bool = True,
    ai_settings_provider: AISettingsProvider | None = None,
) -> HelpdeskComponentDependencies:
    return HelpdeskComponentDependencies(
        tickets=HelpdeskTicketDependencies(
            ticket_repository=bundle.ticket,
            ticket_analytics_repository=bundle.ticket_analytics,
            ticket_feedback_repository=bundle.ticket_feedback,
            ticket_ai_summary_repository=bundle.ticket_ai_summary,
            ticket_message_repository=bundle.ticket_message,
            ticket_internal_note_repository=bundle.ticket_internal_note,
            ticket_event_repository=bundle.ticket_event,
            ticket_tag_repository=bundle.ticket_tag,
        ),
        catalog=HelpdeskCatalogDependencies(
            macro_repository=bundle.macro,
            tag_repository=bundle.tag,
            ticket_category_repository=bundle.ticket_category,
        ),
        operators=HelpdeskOperatorDependencies(
            operator_repository=bundle.operator,
            operator_invite_repository=bundle.operator_invite,
            super_admin_telegram_user_ids=super_admin_telegram_user_ids,
        ),
        sla=HelpdeskSLADependencies(sla_policy_repository=bundle.sla_policy),
        ai=HelpdeskAIDependencies(
            ai_client_factory=ai_client_factory,
            ai_settings_provider=ai_settings_provider or InMemoryAISettingsRepository(),
        ),
        feedback_audit_stats=HelpdeskFeedbackAuditStatsDependencies(
            export_renderers=export_renderers,
            include_internal_notes_in_ticket_reports=include_internal_notes_in_ticket_reports,
        ),
    )


@dataclass(slots=True, frozen=True)
class HelpdeskTicketUseCases:
    create_from_client_message: CreateTicketFromClientMessageUseCase
    get_active_client_ticket: GetActiveClientTicketUseCase
    get_feedback: GetTicketFeedbackUseCase
    submit_feedback_rating: SubmitTicketFeedbackRatingUseCase
    add_feedback_comment: AddTicketFeedbackCommentUseCase
    add_message: AddMessageToTicketUseCase
    add_internal_note: AddInternalNoteToTicketUseCase
    assign_ticket: AssignTicketToOperatorUseCase
    get_next_queued: GetNextQueuedTicketUseCase
    list_queued: ListQueuedTicketsUseCase
    list_operator_tickets: ListOperatorTicketsUseCase
    list_archived_tickets: ListArchivedTicketsUseCase
    assign_next_queued: AssignNextQueuedTicketUseCase
    get_details: GetTicketDetailsUseCase
    export_report: ExportTicketReportUseCase
    reply_as_operator: ReplyToTicketAsOperatorUseCase
    close_ticket: CloseTicketUseCase
    escalate_ticket: EscalateTicketUseCase
    basic_stats: BasicStatsUseCase


@dataclass(slots=True, frozen=True)
class HelpdeskOperatorUseCases:
    list_operators: ListOperatorsUseCase
    promote_operator: PromoteOperatorUseCase
    revoke_operator: RevokeOperatorUseCase
    create_operator_invite: CreateOperatorInviteCodeUseCase
    preview_operator_invite: PreviewOperatorInviteCodeUseCase
    redeem_operator_invite: RedeemOperatorInviteCodeUseCase
    export_analytics_snapshot: ExportAnalyticsSnapshotUseCase


@dataclass(slots=True, frozen=True)
class HelpdeskCatalogUseCases:
    list_ticket_categories: ListTicketCategoriesUseCase
    get_ticket_category: GetTicketCategoryUseCase
    create_ticket_category: CreateTicketCategoryUseCase
    update_ticket_category_title: UpdateTicketCategoryTitleUseCase
    set_ticket_category_active: SetTicketCategoryActiveUseCase
    list_macros: ListMacrosUseCase
    get_macro: GetMacroUseCase
    create_macro: CreateMacroUseCase
    update_macro_title: UpdateMacroTitleUseCase
    update_macro_body: UpdateMacroBodyUseCase
    delete_macro: DeleteMacroUseCase
    apply_macro: ApplyMacroToTicketUseCase
    list_ticket_tags: ListTicketTagsUseCase
    list_available_tags: ListAvailableTagsUseCase
    add_tag: AddTagToTicketUseCase
    remove_tag: RemoveTagFromTicketUseCase


@dataclass(slots=True, frozen=True)
class HelpdeskSLAUseCases:
    evaluate_ticket_state: EvaluateTicketSLAStateUseCase
    auto_escalate_ticket: AutoEscalateTicketBySLAUseCase
    auto_reassign_ticket: AutoReassignTicketBySLAUseCase
    run_checks: RunTicketSLAChecksUseCase


@dataclass(slots=True, frozen=True)
class HelpdeskAIUseCases:
    build_ticket_assist_snapshot: BuildTicketAssistSnapshotUseCase
    generate_ticket_reply_draft: GenerateTicketReplyDraftUseCase
    predict_ticket_category: PredictTicketCategoryUseCase


@dataclass(slots=True, frozen=True)
class HelpdeskComponents:
    permissions: HelpdeskPermissionGuard
    tickets: HelpdeskTicketUseCases
    operators: HelpdeskOperatorUseCases
    catalog: HelpdeskCatalogUseCases
    sla: HelpdeskSLAUseCases
    ai: HelpdeskAIUseCases
    stats: HelpdeskStatsService


def build_helpdesk_components(deps: HelpdeskComponentDependencies) -> HelpdeskComponents:
    ticket_deps = deps.tickets
    catalog_deps = deps.catalog
    operator_deps = deps.operators
    sla_deps = deps.sla
    ai_deps = deps.ai
    feedback_deps = deps.feedback_audit_stats
    stats_service = HelpdeskStatsService(
        analytics_repository=ticket_deps.ticket_analytics_repository
    )
    return _build_helpdesk_components(
        ticket_deps=ticket_deps,
        catalog_deps=catalog_deps,
        operator_deps=operator_deps,
        sla_deps=sla_deps,
        ai_deps=ai_deps,
        feedback_deps=feedback_deps,
        stats_service=stats_service,
    )


def build_helpdesk_component_dependencies(
    bundle: HelpdeskRepositoryBundle,
    *,
    ai_client_factory: AIServiceClientFactory,
    super_admin_telegram_user_ids: frozenset[int],
    export_renderers: HelpdeskExportRenderers,
    include_internal_notes_in_ticket_reports: bool = True,
    ai_settings_provider: AISettingsProvider | None = None,
) -> HelpdeskComponentDependencies:
    return _deps_from_bundle(
        bundle,
        super_admin_telegram_user_ids=super_admin_telegram_user_ids,
        ai_client_factory=ai_client_factory,
        export_renderers=export_renderers,
        include_internal_notes_in_ticket_reports=include_internal_notes_in_ticket_reports,
        ai_settings_provider=ai_settings_provider,
    )


def _build_helpdesk_components(
    *,
    ticket_deps: HelpdeskTicketDependencies,
    catalog_deps: HelpdeskCatalogDependencies,
    operator_deps: HelpdeskOperatorDependencies,
    sla_deps: HelpdeskSLADependencies,
    ai_deps: HelpdeskAIDependencies,
    feedback_deps: HelpdeskFeedbackAuditStatsDependencies,
    stats_service: HelpdeskStatsService,
) -> HelpdeskComponents:
    add_message_to_ticket = AddMessageToTicketUseCase(
        ticket_repository=ticket_deps.ticket_repository,
        ticket_message_repository=ticket_deps.ticket_message_repository,
        ticket_event_repository=ticket_deps.ticket_event_repository,
        ai_client_factory=ai_deps.ai_client_factory,
    )
    return HelpdeskComponents(
        permissions=HelpdeskPermissionGuard(
            operator_repository=operator_deps.operator_repository,
            super_admin_telegram_user_ids=operator_deps.super_admin_telegram_user_ids,
        ),
        tickets=HelpdeskTicketUseCases(
            create_from_client_message=CreateTicketFromClientMessageUseCase(
                ticket_repository=ticket_deps.ticket_repository,
                ticket_event_repository=ticket_deps.ticket_event_repository,
                add_message_to_ticket=add_message_to_ticket,
            ),
            get_active_client_ticket=GetActiveClientTicketUseCase(
                ticket_repository=ticket_deps.ticket_repository
            ),
            get_feedback=GetTicketFeedbackUseCase(
                ticket_repository=ticket_deps.ticket_repository,
                ticket_feedback_repository=ticket_deps.ticket_feedback_repository,
            ),
            submit_feedback_rating=SubmitTicketFeedbackRatingUseCase(
                ticket_repository=ticket_deps.ticket_repository,
                ticket_feedback_repository=ticket_deps.ticket_feedback_repository,
            ),
            add_feedback_comment=AddTicketFeedbackCommentUseCase(
                ticket_repository=ticket_deps.ticket_repository,
                ticket_feedback_repository=ticket_deps.ticket_feedback_repository,
            ),
            add_message=add_message_to_ticket,
            add_internal_note=AddInternalNoteToTicketUseCase(
                ticket_repository=ticket_deps.ticket_repository,
                ticket_internal_note_repository=ticket_deps.ticket_internal_note_repository,
                operator_repository=operator_deps.operator_repository,
            ),
            assign_ticket=AssignTicketToOperatorUseCase(
                ticket_repository=ticket_deps.ticket_repository,
                ticket_event_repository=ticket_deps.ticket_event_repository,
                operator_repository=operator_deps.operator_repository,
            ),
            get_next_queued=GetNextQueuedTicketUseCase(
                ticket_repository=ticket_deps.ticket_repository
            ),
            list_queued=ListQueuedTicketsUseCase(ticket_repository=ticket_deps.ticket_repository),
            list_operator_tickets=ListOperatorTicketsUseCase(
                ticket_repository=ticket_deps.ticket_repository
            ),
            list_archived_tickets=ListArchivedTicketsUseCase(
                ticket_repository=ticket_deps.ticket_repository
            ),
            assign_next_queued=AssignNextQueuedTicketUseCase(
                ticket_repository=ticket_deps.ticket_repository,
                ticket_event_repository=ticket_deps.ticket_event_repository,
                operator_repository=operator_deps.operator_repository,
            ),
            get_details=GetTicketDetailsUseCase(ticket_repository=ticket_deps.ticket_repository),
            export_report=ExportTicketReportUseCase(
                ticket_repository=ticket_deps.ticket_repository,
                ticket_feedback_repository=ticket_deps.ticket_feedback_repository,
                ticket_event_repository=ticket_deps.ticket_event_repository,
                csv_renderer=feedback_deps.export_renderers.ticket_report_csv,
                html_renderer=feedback_deps.export_renderers.ticket_report_html,
                include_internal_notes=feedback_deps.include_internal_notes_in_ticket_reports,
            ),
            reply_as_operator=ReplyToTicketAsOperatorUseCase(
                ticket_repository=ticket_deps.ticket_repository,
                operator_repository=operator_deps.operator_repository,
                add_message_to_ticket=add_message_to_ticket,
            ),
            close_ticket=CloseTicketUseCase(
                ticket_repository=ticket_deps.ticket_repository,
                ticket_event_repository=ticket_deps.ticket_event_repository,
            ),
            escalate_ticket=EscalateTicketUseCase(
                ticket_repository=ticket_deps.ticket_repository,
                ticket_event_repository=ticket_deps.ticket_event_repository,
            ),
            basic_stats=BasicStatsUseCase(ticket_repository=ticket_deps.ticket_repository),
        ),
        operators=HelpdeskOperatorUseCases(
            list_operators=ListOperatorsUseCase(
                operator_repository=operator_deps.operator_repository,
                super_admin_telegram_user_ids=operator_deps.super_admin_telegram_user_ids,
            ),
            promote_operator=PromoteOperatorUseCase(
                operator_repository=operator_deps.operator_repository,
                super_admin_telegram_user_ids=operator_deps.super_admin_telegram_user_ids,
            ),
            revoke_operator=RevokeOperatorUseCase(
                operator_repository=operator_deps.operator_repository,
                super_admin_telegram_user_ids=operator_deps.super_admin_telegram_user_ids,
            ),
            create_operator_invite=CreateOperatorInviteCodeUseCase(
                operator_invite_repository=operator_deps.operator_invite_repository
            ),
            preview_operator_invite=PreviewOperatorInviteCodeUseCase(
                operator_invite_repository=operator_deps.operator_invite_repository
            ),
            redeem_operator_invite=RedeemOperatorInviteCodeUseCase(
                operator_invite_repository=operator_deps.operator_invite_repository,
                operator_repository=operator_deps.operator_repository,
                super_admin_telegram_user_ids=operator_deps.super_admin_telegram_user_ids,
            ),
            export_analytics_snapshot=ExportAnalyticsSnapshotUseCase(
                stats_service=stats_service,
                csv_renderer=feedback_deps.export_renderers.analytics_snapshot_csv,
                html_renderer=feedback_deps.export_renderers.analytics_snapshot_html,
            ),
        ),
        catalog=HelpdeskCatalogUseCases(
            list_ticket_categories=ListTicketCategoriesUseCase(
                ticket_category_repository=catalog_deps.ticket_category_repository
            ),
            get_ticket_category=GetTicketCategoryUseCase(
                ticket_category_repository=catalog_deps.ticket_category_repository
            ),
            create_ticket_category=CreateTicketCategoryUseCase(
                ticket_category_repository=catalog_deps.ticket_category_repository
            ),
            update_ticket_category_title=UpdateTicketCategoryTitleUseCase(
                ticket_category_repository=catalog_deps.ticket_category_repository
            ),
            set_ticket_category_active=SetTicketCategoryActiveUseCase(
                ticket_category_repository=catalog_deps.ticket_category_repository
            ),
            list_macros=ListMacrosUseCase(macro_repository=catalog_deps.macro_repository),
            get_macro=GetMacroUseCase(macro_repository=catalog_deps.macro_repository),
            create_macro=CreateMacroUseCase(macro_repository=catalog_deps.macro_repository),
            update_macro_title=UpdateMacroTitleUseCase(
                macro_repository=catalog_deps.macro_repository
            ),
            update_macro_body=UpdateMacroBodyUseCase(
                macro_repository=catalog_deps.macro_repository
            ),
            delete_macro=DeleteMacroUseCase(macro_repository=catalog_deps.macro_repository),
            apply_macro=ApplyMacroToTicketUseCase(
                ticket_repository=ticket_deps.ticket_repository,
                ticket_message_repository=ticket_deps.ticket_message_repository,
                ticket_event_repository=ticket_deps.ticket_event_repository,
                operator_repository=operator_deps.operator_repository,
                macro_repository=catalog_deps.macro_repository,
            ),
            list_ticket_tags=ListTicketTagsUseCase(
                ticket_repository=ticket_deps.ticket_repository,
                ticket_tag_repository=ticket_deps.ticket_tag_repository,
            ),
            list_available_tags=ListAvailableTagsUseCase(
                tag_repository=catalog_deps.tag_repository
            ),
            add_tag=AddTagToTicketUseCase(
                ticket_repository=ticket_deps.ticket_repository,
                tag_repository=catalog_deps.tag_repository,
                ticket_tag_repository=ticket_deps.ticket_tag_repository,
                ticket_event_repository=ticket_deps.ticket_event_repository,
            ),
            remove_tag=RemoveTagFromTicketUseCase(
                ticket_repository=ticket_deps.ticket_repository,
                tag_repository=catalog_deps.tag_repository,
                ticket_tag_repository=ticket_deps.ticket_tag_repository,
                ticket_event_repository=ticket_deps.ticket_event_repository,
            ),
        ),
        sla=HelpdeskSLAUseCases(
            evaluate_ticket_state=EvaluateTicketSLAStateUseCase(
                ticket_repository=ticket_deps.ticket_repository,
                sla_policy_repository=sla_deps.sla_policy_repository,
            ),
            auto_escalate_ticket=AutoEscalateTicketBySLAUseCase(
                ticket_repository=ticket_deps.ticket_repository,
                ticket_event_repository=ticket_deps.ticket_event_repository,
                sla_policy_repository=sla_deps.sla_policy_repository,
            ),
            auto_reassign_ticket=AutoReassignTicketBySLAUseCase(
                ticket_repository=ticket_deps.ticket_repository,
                ticket_event_repository=ticket_deps.ticket_event_repository,
                operator_repository=operator_deps.operator_repository,
                sla_policy_repository=sla_deps.sla_policy_repository,
            ),
            run_checks=RunTicketSLAChecksUseCase(
                ticket_repository=ticket_deps.ticket_repository,
                ticket_event_repository=ticket_deps.ticket_event_repository,
                operator_repository=operator_deps.operator_repository,
                sla_policy_repository=sla_deps.sla_policy_repository,
            ),
        ),
        ai=HelpdeskAIUseCases(
            build_ticket_assist_snapshot=BuildTicketAssistSnapshotUseCase(
                ticket_repository=ticket_deps.ticket_repository,
                ticket_ai_summary_repository=ticket_deps.ticket_ai_summary_repository,
                macro_repository=catalog_deps.macro_repository,
                ai_client_factory=ai_deps.ai_client_factory,
                ai_settings_provider=ai_deps.ai_settings_provider,
            ),
            generate_ticket_reply_draft=GenerateTicketReplyDraftUseCase(
                ticket_repository=ticket_deps.ticket_repository,
                ticket_ai_summary_repository=ticket_deps.ticket_ai_summary_repository,
                ai_client_factory=ai_deps.ai_client_factory,
                ai_settings_provider=ai_deps.ai_settings_provider,
            ),
            predict_ticket_category=PredictTicketCategoryUseCase(
                ticket_category_repository=catalog_deps.ticket_category_repository,
                ai_client_factory=ai_deps.ai_client_factory,
                ai_settings_provider=ai_deps.ai_settings_provider,
            ),
        ),
        stats=stats_service,
    )
