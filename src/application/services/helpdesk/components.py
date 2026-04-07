from __future__ import annotations

from dataclasses import dataclass

from application.services.helpdesk.permissions import HelpdeskPermissionGuard
from application.services.stats import HelpdeskStatsService
from application.use_cases.tickets.creation import CreateTicketFromClientMessageUseCase
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
    AddMessageToTicketUseCase,
    ReplyToTicketAsOperatorUseCase,
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
    OperatorRepository,
    SLAPolicyRepository,
    TagRepository,
    TicketEventRepository,
    TicketMessageRepository,
    TicketRepository,
    TicketTagRepository,
)


@dataclass(slots=True, frozen=True)
class HelpdeskTicketUseCases:
    create_from_client_message: CreateTicketFromClientMessageUseCase
    add_message: AddMessageToTicketUseCase
    assign_ticket: AssignTicketToOperatorUseCase
    get_next_queued: GetNextQueuedTicketUseCase
    list_queued: ListQueuedTicketsUseCase
    list_operator_tickets: ListOperatorTicketsUseCase
    assign_next_queued: AssignNextQueuedTicketUseCase
    get_details: GetTicketDetailsUseCase
    reply_as_operator: ReplyToTicketAsOperatorUseCase
    close_ticket: CloseTicketUseCase
    escalate_ticket: EscalateTicketUseCase
    basic_stats: BasicStatsUseCase


@dataclass(slots=True, frozen=True)
class HelpdeskOperatorUseCases:
    list_operators: ListOperatorsUseCase
    promote_operator: PromoteOperatorUseCase
    revoke_operator: RevokeOperatorUseCase


@dataclass(slots=True, frozen=True)
class HelpdeskCatalogUseCases:
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
    ticket_message_repository: TicketMessageRepository,
    ticket_event_repository: TicketEventRepository,
    operator_repository: OperatorRepository,
    macro_repository: MacroRepository,
    sla_policy_repository: SLAPolicyRepository,
    tag_repository: TagRepository,
    ticket_tag_repository: TicketTagRepository,
    super_admin_telegram_user_ids: frozenset[int],
) -> HelpdeskComponents:
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
            add_message=AddMessageToTicketUseCase(
                ticket_repository=ticket_repository,
                ticket_message_repository=ticket_message_repository,
                ticket_event_repository=ticket_event_repository,
            ),
            assign_ticket=AssignTicketToOperatorUseCase(
                ticket_repository=ticket_repository,
                ticket_event_repository=ticket_event_repository,
                operator_repository=operator_repository,
            ),
            get_next_queued=GetNextQueuedTicketUseCase(ticket_repository=ticket_repository),
            list_queued=ListQueuedTicketsUseCase(ticket_repository=ticket_repository),
            list_operator_tickets=ListOperatorTicketsUseCase(ticket_repository=ticket_repository),
            assign_next_queued=AssignNextQueuedTicketUseCase(
                ticket_repository=ticket_repository,
                ticket_event_repository=ticket_event_repository,
                operator_repository=operator_repository,
            ),
            get_details=GetTicketDetailsUseCase(ticket_repository=ticket_repository),
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
        ),
        catalog=HelpdeskCatalogUseCases(
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
        stats=HelpdeskStatsService(ticket_repository=ticket_repository),
    )
