from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from enum import StrEnum

from domain.contracts.repositories import OperatorRepository
from domain.enums.roles import UserRole

AuthorizationServiceFactory = Callable[[], AbstractAsyncContextManager["AuthorizationService"]]


class Permission(StrEnum):
    ACCESS_OPERATOR = "access_operator"
    MANAGE_OPERATORS = "manage_operators"
    ACCESS_ADMIN = "access_admin"
    VIEW_TICKET = "view_ticket"
    CREATE_TICKET = "create_ticket"
    CLIENT_REPLY = "client_reply"
    OPERATOR_REPLY = "operator_reply"
    CLOSE_TICKET = "close_ticket"
    ASSIGN_TICKET = "assign_ticket"
    ADD_INTERNAL_NOTE = "add_internal_note"
    USE_AI_ASSIST = "use_ai_assist"
    MANAGE_CATEGORIES = "manage_categories"
    MANAGE_MACROS = "manage_macros"
    CREATE_OPERATOR_INVITES = "create_operator_invites"
    ACCEPT_OPERATOR_INVITES = "accept_operator_invites"
    EXPORT_TICKETS = "export_tickets"
    EXPORT_ANALYTICS = "export_analytics"


CLIENT_PERMISSIONS = frozenset(
    {
        Permission.VIEW_TICKET,
        Permission.CREATE_TICKET,
        Permission.CLIENT_REPLY,
        Permission.CLOSE_TICKET,
        Permission.ACCEPT_OPERATOR_INVITES,
    }
)

OPERATOR_PERMISSIONS = CLIENT_PERMISSIONS | frozenset(
    {
        Permission.ACCESS_OPERATOR,
        Permission.OPERATOR_REPLY,
        Permission.CLOSE_TICKET,
        Permission.ASSIGN_TICKET,
        Permission.ADD_INTERNAL_NOTE,
        Permission.USE_AI_ASSIST,
        Permission.MANAGE_CATEGORIES,
        Permission.MANAGE_MACROS,
        Permission.EXPORT_TICKETS,
        Permission.EXPORT_ANALYTICS,
    }
)

SUPER_ADMIN_PERMISSIONS = OPERATOR_PERMISSIONS | frozenset(
    {
        Permission.ACCESS_ADMIN,
        Permission.MANAGE_OPERATORS,
        Permission.CREATE_OPERATOR_INVITES,
    }
)


ROLE_PERMISSIONS: dict[UserRole, frozenset[Permission]] = {
    UserRole.SUPER_ADMIN: SUPER_ADMIN_PERMISSIONS,
    UserRole.OPERATOR: OPERATOR_PERMISSIONS,
    UserRole.USER: CLIENT_PERMISSIONS,
}

INTERNAL_SERVICE_PERMISSIONS = SUPER_ADMIN_PERMISSIONS


def get_permission_denied_message(permission: Permission) -> str:
    if permission in {
        Permission.MANAGE_OPERATORS,
        Permission.ACCESS_ADMIN,
        Permission.CREATE_OPERATOR_INVITES,
    }:
        return "Доступно только суперадминистраторам."
    return "Доступно только операторам и суперадминистраторам."


class AuthorizationError(Exception):
    """Raised when the caller lacks required authorization."""

    def __init__(
        self,
        permission: Permission,
        message: str | None = None,
    ) -> None:
        self.permission = permission
        super().__init__(message or get_permission_denied_message(permission))


@dataclass(slots=True, frozen=True)
class AuthorizationContext:
    telegram_user_id: int
    role: UserRole

    def has_permission(self, permission: Permission) -> bool:
        return permission in ROLE_PERMISSIONS[self.role]


@dataclass(slots=True)
class AuthorizationService:
    operator_repository: OperatorRepository
    super_admin_telegram_user_ids: frozenset[int]

    async def resolve_role(self, *, telegram_user_id: int | None) -> UserRole:
        if telegram_user_id is None:
            return UserRole.USER

        if telegram_user_id in self.super_admin_telegram_user_ids:
            return UserRole.SUPER_ADMIN

        if await self.operator_repository.exists_active_by_telegram_user_id(
            telegram_user_id=telegram_user_id
        ):
            return UserRole.OPERATOR

        return UserRole.USER

    async def resolve_context(
        self,
        *,
        telegram_user_id: int | None,
    ) -> AuthorizationContext | None:
        if telegram_user_id is None:
            return None

        role = await self.resolve_role(telegram_user_id=telegram_user_id)
        return AuthorizationContext(
            telegram_user_id=telegram_user_id,
            role=role,
        )

    async def has_permission(
        self,
        *,
        telegram_user_id: int | None,
        permission: Permission,
    ) -> bool:
        role = await self.resolve_role(telegram_user_id=telegram_user_id)
        return permission in ROLE_PERMISSIONS[role]
