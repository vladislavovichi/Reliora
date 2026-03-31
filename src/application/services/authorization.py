from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from enum import Enum

from domain.contracts.repositories import OperatorRepository
from domain.enums.roles import UserRole

AuthorizationServiceFactory = Callable[[], AbstractAsyncContextManager["AuthorizationService"]]


class Permission(str, Enum):
    ACCESS_OPERATOR = "access_operator"
    MANAGE_OPERATORS = "manage_operators"
    ACCESS_ADMIN = "access_admin"


ROLE_PERMISSIONS: dict[UserRole, frozenset[Permission]] = {
    UserRole.SUPER_ADMIN: frozenset(
        {
            Permission.ACCESS_OPERATOR,
            Permission.MANAGE_OPERATORS,
            Permission.ACCESS_ADMIN,
        }
    ),
    UserRole.OPERATOR: frozenset({Permission.ACCESS_OPERATOR}),
    UserRole.USER: frozenset(),
}


@dataclass(slots=True, frozen=True)
class AuthorizationContext:
    telegram_user_id: int
    role: UserRole

    def has_permission(self, permission: Permission) -> bool:
        return permission in ROLE_PERMISSIONS[self.role]


@dataclass(slots=True)
class AuthorizationService:
    operator_repository: OperatorRepository
    super_admin_telegram_user_id: int

    async def resolve_role(self, *, telegram_user_id: int | None) -> UserRole:
        if telegram_user_id is None:
            return UserRole.USER

        if telegram_user_id == self.super_admin_telegram_user_id:
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
