from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from application.services.helpdesk.permissions import HelpdeskPermissionGuard
from application.services.stats import HelpdeskStatsService
from application.use_cases.analytics.exports import ExportAnalyticsSnapshotUseCase
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
from application.use_cases.tickets.exports import ExportTicketReportUseCase
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
    MacroRepository,
    OperatorInviteCodeRepository,
    OperatorRepository,
    SLAPolicyRepository,
    TagRepository,
    TicketAnalyticsRepository,
    TicketCategoryRepository,
    TicketEventRepository,
    TicketFeedbackRepository,
    TicketInternalNoteRepository,
    TicketMessageRepository,
    TicketRepository,
    TicketTagRepository,
)
from infrastructure.exports.analytics_snapshot_csv import render_analytics_snapshot_csv
from infrastructure.exports.analytics_snapshot_html import render_analytics_snapshot_html
from infrastructure.exports.ticket_report_csv import render_ticket_report_csv
from infrastructure.exports.ticket_report_html import render_ticket_report_html


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
class HelpdeskComponents:
    permissions: HelpdeskPermissionGuard
    tickets: HelpdeskTicketUseCases
    operators: HelpdeskOperatorUseCases
    catalog: HelpdeskCatalogUseCases
    sla: HelpdeskSLAUseCases
    stats: HelpdeskStatsService


def build_helpdesk_components(
    *,
    ticket_repository: TicketRepository,
    ticket_feedback_repository: TicketFeedbackRepository,
    ticket_message_repository: TicketMessageRepository,
    ticket_internal_note_repository: TicketInternalNoteRepository,
    ticket_event_repository: TicketEventRepository,
    operator_repository: OperatorRepository,
    operator_invite_repository: OperatorInviteCodeRepository,
    macro_repository: MacroRepository,
    sla_policy_repository: SLAPolicyRepository,
    tag_repository: TagRepository,
    ticket_category_repository: TicketCategoryRepository,
    ticket_tag_repository: TicketTagRepository,
    super_admin_telegram_user_ids: frozenset[int],
    include_internal_notes_in_ticket_reports: bool = True,
) -> HelpdeskComponents:
    stats_service = HelpdeskStatsService(
        analytics_repository=cast(TicketAnalyticsRepository, ticket_repository)
    )
    return HelpdeskComponents(
        permissions=HelpdeskPermissionGuard(
            operator_repository=operator_repository,
            super_admin_telegram_user_ids=super_admin_telegram_user_ids,
        ),
        tickets=HelpdeskTicketUseCases(
            create_from_client_message=CreateTicketFromClientMessageUseCase(
                ticket_repository=ticket_repository,
                ticket_message_repository=ticket_message_repository,
                ticket_event_repository=ticket_event_repository,
            ),
            get_active_client_ticket=GetActiveClientTicketUseCase(
                ticket_repository=ticket_repository
            ),
            get_feedback=GetTicketFeedbackUseCase(
                ticket_repository=ticket_repository,
                ticket_feedback_repository=ticket_feedback_repository,
            ),
            submit_feedback_rating=SubmitTicketFeedbackRatingUseCase(
                ticket_repository=ticket_repository,
                ticket_feedback_repository=ticket_feedback_repository,
            ),
            add_feedback_comment=AddTicketFeedbackCommentUseCase(
                ticket_repository=ticket_repository,
                ticket_feedback_repository=ticket_feedback_repository,
            ),
            add_message=AddMessageToTicketUseCase(
                ticket_repository=ticket_repository,
                ticket_message_repository=ticket_message_repository,
                ticket_event_repository=ticket_event_repository,
            ),
            add_internal_note=AddInternalNoteToTicketUseCase(
                ticket_repository=ticket_repository,
                ticket_internal_note_repository=ticket_internal_note_repository,
                operator_repository=operator_repository,
            ),
            assign_ticket=AssignTicketToOperatorUseCase(
                ticket_repository=ticket_repository,
                ticket_event_repository=ticket_event_repository,
                operator_repository=operator_repository,
            ),
            get_next_queued=GetNextQueuedTicketUseCase(ticket_repository=ticket_repository),
            list_queued=ListQueuedTicketsUseCase(ticket_repository=ticket_repository),
            list_operator_tickets=ListOperatorTicketsUseCase(ticket_repository=ticket_repository),
            list_archived_tickets=ListArchivedTicketsUseCase(ticket_repository=ticket_repository),
            assign_next_queued=AssignNextQueuedTicketUseCase(
                ticket_repository=ticket_repository,
                ticket_event_repository=ticket_event_repository,
                operator_repository=operator_repository,
            ),
            get_details=GetTicketDetailsUseCase(ticket_repository=ticket_repository),
            export_report=ExportTicketReportUseCase(
                ticket_repository=ticket_repository,
                ticket_feedback_repository=ticket_feedback_repository,
                ticket_event_repository=ticket_event_repository,
                csv_renderer=render_ticket_report_csv,
                html_renderer=render_ticket_report_html,
                include_internal_notes=include_internal_notes_in_ticket_reports,
            ),
            reply_as_operator=ReplyToTicketAsOperatorUseCase(
                ticket_repository=ticket_repository,
                ticket_message_repository=ticket_message_repository,
                ticket_event_repository=ticket_event_repository,
                operator_repository=operator_repository,
            ),
            close_ticket=CloseTicketUseCase(
                ticket_repository=ticket_repository,
                ticket_event_repository=ticket_event_repository,
            ),
            escalate_ticket=EscalateTicketUseCase(
                ticket_repository=ticket_repository,
                ticket_event_repository=ticket_event_repository,
            ),
            basic_stats=BasicStatsUseCase(ticket_repository=ticket_repository),
        ),
        operators=HelpdeskOperatorUseCases(
            list_operators=ListOperatorsUseCase(
                operator_repository=operator_repository,
                super_admin_telegram_user_ids=super_admin_telegram_user_ids,
            ),
            promote_operator=PromoteOperatorUseCase(
                operator_repository=operator_repository,
                super_admin_telegram_user_ids=super_admin_telegram_user_ids,
            ),
            revoke_operator=RevokeOperatorUseCase(
                operator_repository=operator_repository,
                super_admin_telegram_user_ids=super_admin_telegram_user_ids,
            ),
            create_operator_invite=CreateOperatorInviteCodeUseCase(
                operator_invite_repository=operator_invite_repository
            ),
            preview_operator_invite=PreviewOperatorInviteCodeUseCase(
                operator_invite_repository=operator_invite_repository
            ),
            redeem_operator_invite=RedeemOperatorInviteCodeUseCase(
                operator_invite_repository=operator_invite_repository,
                operator_repository=operator_repository,
                super_admin_telegram_user_ids=super_admin_telegram_user_ids,
            ),
            export_analytics_snapshot=ExportAnalyticsSnapshotUseCase(
                stats_service=stats_service,
                csv_renderer=render_analytics_snapshot_csv,
                html_renderer=render_analytics_snapshot_html,
            ),
        ),
        catalog=HelpdeskCatalogUseCases(
            list_ticket_categories=ListTicketCategoriesUseCase(
                ticket_category_repository=ticket_category_repository
            ),
            get_ticket_category=GetTicketCategoryUseCase(
                ticket_category_repository=ticket_category_repository
            ),
            create_ticket_category=CreateTicketCategoryUseCase(
                ticket_category_repository=ticket_category_repository
            ),
            update_ticket_category_title=UpdateTicketCategoryTitleUseCase(
                ticket_category_repository=ticket_category_repository
            ),
            set_ticket_category_active=SetTicketCategoryActiveUseCase(
                ticket_category_repository=ticket_category_repository
            ),
            list_macros=ListMacrosUseCase(macro_repository=macro_repository),
            get_macro=GetMacroUseCase(macro_repository=macro_repository),
            create_macro=CreateMacroUseCase(macro_repository=macro_repository),
            update_macro_title=UpdateMacroTitleUseCase(macro_repository=macro_repository),
            update_macro_body=UpdateMacroBodyUseCase(macro_repository=macro_repository),
            delete_macro=DeleteMacroUseCase(macro_repository=macro_repository),
            apply_macro=ApplyMacroToTicketUseCase(
                ticket_repository=ticket_repository,
                ticket_message_repository=ticket_message_repository,
                ticket_event_repository=ticket_event_repository,
                operator_repository=operator_repository,
                macro_repository=macro_repository,
            ),
            list_ticket_tags=ListTicketTagsUseCase(
                ticket_repository=ticket_repository,
                ticket_tag_repository=ticket_tag_repository,
            ),
            list_available_tags=ListAvailableTagsUseCase(tag_repository=tag_repository),
            add_tag=AddTagToTicketUseCase(
                ticket_repository=ticket_repository,
                tag_repository=tag_repository,
                ticket_tag_repository=ticket_tag_repository,
                ticket_event_repository=ticket_event_repository,
            ),
            remove_tag=RemoveTagFromTicketUseCase(
                ticket_repository=ticket_repository,
                tag_repository=tag_repository,
                ticket_tag_repository=ticket_tag_repository,
                ticket_event_repository=ticket_event_repository,
            ),
        ),
        sla=HelpdeskSLAUseCases(
            evaluate_ticket_state=EvaluateTicketSLAStateUseCase(
                ticket_repository=ticket_repository,
                sla_policy_repository=sla_policy_repository,
            ),
            auto_escalate_ticket=AutoEscalateTicketBySLAUseCase(
                ticket_repository=ticket_repository,
                ticket_event_repository=ticket_event_repository,
                sla_policy_repository=sla_policy_repository,
            ),
            auto_reassign_ticket=AutoReassignTicketBySLAUseCase(
                ticket_repository=ticket_repository,
                ticket_event_repository=ticket_event_repository,
                operator_repository=operator_repository,
                sla_policy_repository=sla_policy_repository,
            ),
            run_checks=RunTicketSLAChecksUseCase(
                ticket_repository=ticket_repository,
                ticket_event_repository=ticket_event_repository,
                operator_repository=operator_repository,
                sla_policy_repository=sla_policy_repository,
            ),
        ),
        stats=stats_service,
    )
