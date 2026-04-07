from __future__ import annotations

from dataclasses import dataclass
from typing import NoReturn

from application.services.authorization import (
    AuthorizationError,
    AuthorizationService,
    Permission,
    get_permission_denied_message,
)
from domain.enums.roles import UserRole


@dataclass(slots=True)
class FakeOperatorRepository:
    active_operator_ids: set[int]

    async def exists_active_by_telegram_user_id(self, *, telegram_user_id: int) -> bool:
        return telegram_user_id in self.active_operator_ids

    async def list_active(self) -> NoReturn:
        raise NotImplementedError

    async def promote(
        self,
        *,
        telegram_user_id: int,
        display_name: str,
        username: str | None = None,
    ) -> NoReturn:
        raise NotImplementedError

    async def revoke(self, *, telegram_user_id: int) -> NoReturn:
        raise NotImplementedError

    async def get_or_create(
        self,
        *,
        telegram_user_id: int,
        display_name: str,
        username: str | None = None,
    ) -> NoReturn:
        raise NotImplementedError


async def test_resolve_role_returns_super_admin_from_config() -> None:
    service = AuthorizationService(
        operator_repository=FakeOperatorRepository(active_operator_ids={42, 1001}),
        super_admin_telegram_user_ids=frozenset({42}),
    )

    result = await service.resolve_role(telegram_user_id=42)

    assert result == UserRole.SUPER_ADMIN


async def test_resolve_role_returns_operator_from_repository() -> None:
    service = AuthorizationService(
        operator_repository=FakeOperatorRepository(active_operator_ids={1001}),
        super_admin_telegram_user_ids=frozenset({42}),
    )

    result = await service.resolve_role(telegram_user_id=1001)

    assert result == UserRole.OPERATOR


async def test_resolve_role_falls_back_to_regular_user() -> None:
    service = AuthorizationService(
        operator_repository=FakeOperatorRepository(active_operator_ids={1001}),
        super_admin_telegram_user_ids=frozenset({42}),
    )

    result = await service.resolve_role(telegram_user_id=2002)

    assert result == UserRole.USER


async def test_super_admin_has_all_permissions() -> None:
    service = AuthorizationService(
        operator_repository=FakeOperatorRepository(active_operator_ids=set()),
        super_admin_telegram_user_ids=frozenset({42, 84}),
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
        super_admin_telegram_user_ids=frozenset({42}),
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
        super_admin_telegram_user_ids=frozenset({42}),
    )

    assert (
        await service.has_permission(
            telegram_user_id=2002,
            permission=Permission.ACCESS_OPERATOR,
        )
        is False
    )


def test_get_permission_denied_message_returns_russian_text() -> None:
    assert get_permission_denied_message(Permission.ACCESS_OPERATOR) == (
        "Доступно только операторам и суперадминистраторам."
    )
    assert get_permission_denied_message(Permission.MANAGE_OPERATORS) == (
        "Доступно только суперадминистраторам."
    )


def test_authorization_error_uses_permission_specific_message() -> None:
    assert str(AuthorizationError(Permission.ACCESS_OPERATOR)) == (
        "Доступно только операторам и суперадминистраторам."
    )


async def test_revoked_operator_loses_operator_permissions() -> None:
    repository = FakeOperatorRepository(active_operator_ids={1001})
    service = AuthorizationService(
        operator_repository=repository,
        super_admin_telegram_user_ids=frozenset({42}),
    )

    repository.active_operator_ids.remove(1001)

    result = await service.resolve_role(telegram_user_id=1001)

    assert result == UserRole.USER


async def test_second_super_admin_is_recognized_from_configured_set() -> None:
    service = AuthorizationService(
        operator_repository=FakeOperatorRepository(active_operator_ids={1001}),
        super_admin_telegram_user_ids=frozenset({42, 84}),
    )

    result = await service.resolve_role(telegram_user_id=84)

    assert result == UserRole.SUPER_ADMIN
