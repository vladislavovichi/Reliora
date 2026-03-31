from __future__ import annotations

from dataclasses import dataclass

from application.services.authorization import AuthorizationService, Permission
from domain.enums.roles import UserRole


@dataclass(slots=True)
class FakeOperatorRepository:
    active_operator_ids: set[int]

    async def exists_active_by_telegram_user_id(self, *, telegram_user_id: int) -> bool:
        return telegram_user_id in self.active_operator_ids


async def test_resolve_role_returns_super_admin_from_config() -> None:
    service = AuthorizationService(
        operator_repository=FakeOperatorRepository(active_operator_ids={42, 1001}),
        super_admin_telegram_user_id=42,
    )

    result = await service.resolve_role(telegram_user_id=42)

    assert result == UserRole.SUPER_ADMIN


async def test_resolve_role_returns_operator_from_repository() -> None:
    service = AuthorizationService(
        operator_repository=FakeOperatorRepository(active_operator_ids={1001}),
        super_admin_telegram_user_id=42,
    )

    result = await service.resolve_role(telegram_user_id=1001)

    assert result == UserRole.OPERATOR


async def test_resolve_role_falls_back_to_regular_user() -> None:
    service = AuthorizationService(
        operator_repository=FakeOperatorRepository(active_operator_ids={1001}),
        super_admin_telegram_user_id=42,
    )

    result = await service.resolve_role(telegram_user_id=2002)

    assert result == UserRole.USER


async def test_super_admin_has_all_permissions() -> None:
    service = AuthorizationService(
        operator_repository=FakeOperatorRepository(active_operator_ids=set()),
        super_admin_telegram_user_id=42,
    )

    assert (
        await service.has_permission(
            telegram_user_id=42,
            permission=Permission.ACCESS_OPERATOR,
        )
        is True
    )
    assert (
        await service.has_permission(
            telegram_user_id=42,
            permission=Permission.MANAGE_OPERATORS,
        )
        is True
    )
    assert (
        await service.has_permission(
            telegram_user_id=42,
            permission=Permission.ACCESS_ADMIN,
        )
        is True
    )


async def test_operator_cannot_manage_operators() -> None:
    service = AuthorizationService(
        operator_repository=FakeOperatorRepository(active_operator_ids={1001}),
        super_admin_telegram_user_id=42,
    )

    assert (
        await service.has_permission(
            telegram_user_id=1001,
            permission=Permission.ACCESS_OPERATOR,
        )
        is True
    )
    assert (
        await service.has_permission(
            telegram_user_id=1001,
            permission=Permission.MANAGE_OPERATORS,
        )
        is False
    )


async def test_regular_user_has_no_protected_permissions() -> None:
    service = AuthorizationService(
        operator_repository=FakeOperatorRepository(active_operator_ids={1001}),
        super_admin_telegram_user_id=42,
    )

    assert (
        await service.has_permission(
            telegram_user_id=2002,
            permission=Permission.ACCESS_OPERATOR,
        )
        is False
    )
