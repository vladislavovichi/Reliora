from __future__ import annotations

from collections.abc import Sequence

from application.use_cases.tickets.summaries import (
    OperatorManagementError,
    OperatorRoleMutationResult,
    OperatorSummary,
    build_operator_summary,
)
from domain.contracts.repositories import OperatorRepository


class ListOperatorsUseCase:
    def __init__(
        self,
        operator_repository: OperatorRepository,
        *,
        super_admin_telegram_user_ids: frozenset[int],
    ) -> None:
        self.operator_repository = operator_repository
        self.super_admin_telegram_user_ids = super_admin_telegram_user_ids

    async def __call__(self) -> Sequence[OperatorSummary]:
        operators = await self.operator_repository.list_active()
        return [
            build_operator_summary(operator)
            for operator in operators
            if operator.telegram_user_id not in self.super_admin_telegram_user_ids
        ]


class PromoteOperatorUseCase:
    def __init__(
        self,
        operator_repository: OperatorRepository,
        *,
        super_admin_telegram_user_ids: frozenset[int],
    ) -> None:
        self.operator_repository = operator_repository
        self.super_admin_telegram_user_ids = super_admin_telegram_user_ids

    async def __call__(
        self,
        *,
        telegram_user_id: int,
        display_name: str,
        username: str | None = None,
    ) -> OperatorRoleMutationResult:
        if telegram_user_id in self.super_admin_telegram_user_ids:
            raise OperatorManagementError("Суперадминистратор уже имеет эти права.")

        was_active = await self.operator_repository.exists_active_by_telegram_user_id(
            telegram_user_id=telegram_user_id
        )
        operator = await self.operator_repository.promote(
            telegram_user_id=telegram_user_id,
            display_name=display_name,
            username=username,
        )
        return OperatorRoleMutationResult(
            operator=build_operator_summary(operator),
            changed=not was_active,
        )


class RevokeOperatorUseCase:
    def __init__(
        self,
        operator_repository: OperatorRepository,
        *,
        super_admin_telegram_user_ids: frozenset[int],
    ) -> None:
        self.operator_repository = operator_repository
        self.super_admin_telegram_user_ids = super_admin_telegram_user_ids

    async def __call__(
        self,
        *,
        telegram_user_id: int,
    ) -> OperatorRoleMutationResult | None:
        if telegram_user_id in self.super_admin_telegram_user_ids:
            raise OperatorManagementError("Нельзя снять права у суперадминистратора.")

        operator = await self.operator_repository.revoke(telegram_user_id=telegram_user_id)
        if operator is None:
            return None

        return OperatorRoleMutationResult(
            operator=build_operator_summary(operator),
            changed=True,
        )
