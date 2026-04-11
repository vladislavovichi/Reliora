from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field

from application.services.audit import AuditTrail
from application.services.authorization import Permission
from application.services.helpdesk.catalog_operations import HelpdeskCatalogOperations
from application.services.helpdesk.components import (
    HelpdeskComponents,
    build_helpdesk_components,
)
from application.services.helpdesk.operator_operations import HelpdeskOperatorOperations
from application.services.helpdesk.permissions import HelpdeskPermissionGuard
from application.services.helpdesk.sla_operations import HelpdeskSLAOperations
from application.services.helpdesk.ticket_operations import HelpdeskTicketOperations
from domain.contracts.repositories import (
    AuditLogRepository,
    MacroRepository,
    OperatorInviteCodeRepository,
    OperatorRepository,
    SLAPolicyRepository,
    TagRepository,
    TicketCategoryRepository,
    TicketEventRepository,
    TicketFeedbackRepository,
    TicketInternalNoteRepository,
    TicketMessageRepository,
    TicketRepository,
    TicketTagRepository,
)
from infrastructure.redis.contracts import SLADeadlineScheduler

HelpdeskServiceFactory = Callable[[], AbstractAsyncContextManager["HelpdeskService"]]


@dataclass(slots=True)
class HelpdeskService(
    HelpdeskTicketOperations,
    HelpdeskCatalogOperations,
    HelpdeskOperatorOperations,
    HelpdeskSLAOperations,
):
    ticket_repository: TicketRepository
    ticket_feedback_repository: TicketFeedbackRepository
    ticket_message_repository: TicketMessageRepository
    ticket_internal_note_repository: TicketInternalNoteRepository
    ticket_event_repository: TicketEventRepository
    audit_log_repository: AuditLogRepository
    operator_repository: OperatorRepository
    operator_invite_repository: OperatorInviteCodeRepository
    macro_repository: MacroRepository
    sla_policy_repository: SLAPolicyRepository
    tag_repository: TagRepository
    ticket_category_repository: TicketCategoryRepository
    ticket_tag_repository: TicketTagRepository
    super_admin_telegram_user_ids: frozenset[int]
    include_internal_notes_in_ticket_reports: bool = True
    sla_deadline_scheduler: SLADeadlineScheduler | None = None
    _components: HelpdeskComponents = field(init=False, repr=False)
    _audit: AuditTrail = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.super_admin_telegram_user_ids:
            raise RuntimeError("Не настроены Telegram user id супер администраторов.")

        self._components = build_helpdesk_components(
            ticket_repository=self.ticket_repository,
            ticket_feedback_repository=self.ticket_feedback_repository,
            ticket_message_repository=self.ticket_message_repository,
            ticket_internal_note_repository=self.ticket_internal_note_repository,
            ticket_event_repository=self.ticket_event_repository,
            operator_repository=self.operator_repository,
            operator_invite_repository=self.operator_invite_repository,
            macro_repository=self.macro_repository,
            sla_policy_repository=self.sla_policy_repository,
            tag_repository=self.tag_repository,
            ticket_category_repository=self.ticket_category_repository,
            ticket_tag_repository=self.ticket_tag_repository,
            super_admin_telegram_user_ids=self.super_admin_telegram_user_ids,
            include_internal_notes_in_ticket_reports=self.include_internal_notes_in_ticket_reports,
        )
        self._audit = AuditTrail(self.audit_log_repository)

    async def _ensure_permission(
        self,
        *,
        permission: Permission,
        telegram_user_id: int | None,
    ) -> None:
        await self._permissions.ensure_allowed(
            permission=permission,
            telegram_user_id=telegram_user_id,
        )

    async def _require_permission_if_actor(
        self,
        *,
        permission: Permission,
        actor_telegram_user_id: int | None,
    ) -> None:
        if actor_telegram_user_id is None:
            return
        await self._ensure_permission(
            permission=permission,
            telegram_user_id=actor_telegram_user_id,
        )

    @property
    def _permissions(self) -> HelpdeskPermissionGuard:
        return self._components.permissions
