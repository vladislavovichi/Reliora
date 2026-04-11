from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from application.contracts.actors import OperatorIdentity
from application.use_cases.tickets.summaries import (
    OperatorRoleMutationResult,
    build_operator_summary,
)
from domain.contracts.repositories import (
    OperatorInviteCodeRecord,
    OperatorInviteCodeRepository,
    OperatorRepository,
)

OPERATOR_INVITE_TTL = timedelta(hours=72)
OPERATOR_INVITE_MAX_USES = 1
OPERATOR_INVITE_PREFIX = "opr_"


class OperatorInviteCodeError(Exception):
    """Raised when an operator invite code cannot be created or redeemed."""


@dataclass(slots=True, frozen=True)
class OperatorInviteCodeSummary:
    code: str
    expires_at: datetime
    max_uses: int


@dataclass(slots=True, frozen=True)
class OperatorInviteCodePreview:
    expires_at: datetime
    remaining_uses: int


@dataclass(slots=True, frozen=True)
class OperatorInviteCodeRedemptionResult:
    operator: OperatorRoleMutationResult
    expires_at: datetime


class CreateOperatorInviteCodeUseCase:
    def __init__(self, operator_invite_repository: OperatorInviteCodeRepository) -> None:
        self.operator_invite_repository = operator_invite_repository

    async def __call__(
        self,
        *,
        created_by_telegram_user_id: int,
    ) -> OperatorInviteCodeSummary:
        code = generate_operator_invite_code()
        expires_at = datetime.now(UTC) + OPERATOR_INVITE_TTL
        await self.operator_invite_repository.create(
            code_hash=hash_operator_invite_code(code),
            created_by_telegram_user_id=created_by_telegram_user_id,
            expires_at=expires_at,
            max_uses=OPERATOR_INVITE_MAX_USES,
        )
        return OperatorInviteCodeSummary(
            code=code,
            expires_at=expires_at,
            max_uses=OPERATOR_INVITE_MAX_USES,
        )


class PreviewOperatorInviteCodeUseCase:
    def __init__(self, operator_invite_repository: OperatorInviteCodeRepository) -> None:
        self.operator_invite_repository = operator_invite_repository

    async def __call__(self, *, code: str) -> OperatorInviteCodePreview:
        invite = await _load_active_invite(
            operator_invite_repository=self.operator_invite_repository,
            code=code,
        )
        return OperatorInviteCodePreview(
            expires_at=invite.expires_at,
            remaining_uses=max(invite.max_uses - invite.used_count, 0),
        )


class RedeemOperatorInviteCodeUseCase:
    def __init__(
        self,
        *,
        operator_invite_repository: OperatorInviteCodeRepository,
        operator_repository: OperatorRepository,
        super_admin_telegram_user_ids: frozenset[int],
    ) -> None:
        self.operator_invite_repository = operator_invite_repository
        self.operator_repository = operator_repository
        self.super_admin_telegram_user_ids = super_admin_telegram_user_ids

    async def __call__(
        self,
        *,
        code: str,
        operator: OperatorIdentity,
    ) -> OperatorInviteCodeRedemptionResult:
        if operator.telegram_user_id in self.super_admin_telegram_user_ids:
            raise OperatorInviteCodeError("Этот доступ уже не нужен.")
        if await self.operator_repository.exists_active_by_telegram_user_id(
            telegram_user_id=operator.telegram_user_id
        ):
            raise OperatorInviteCodeError("Вы уже работаете как оператор.")

        invite = await _load_active_invite(
            operator_invite_repository=self.operator_invite_repository,
            code=code,
        )
        promoted_operator = await self.operator_repository.promote(
            telegram_user_id=operator.telegram_user_id,
            display_name=operator.display_name,
            username=operator.username,
        )
        used_at = datetime.now(UTC)
        await self.operator_invite_repository.mark_used(
            invite_id=invite.id,
            telegram_user_id=operator.telegram_user_id,
            used_at=used_at,
        )
        return OperatorInviteCodeRedemptionResult(
            operator=OperatorRoleMutationResult(
                operator=build_operator_summary(promoted_operator),
                changed=True,
            ),
            expires_at=invite.expires_at,
        )


def generate_operator_invite_code() -> str:
    return f"{OPERATOR_INVITE_PREFIX}{secrets.token_urlsafe(18)}"


def hash_operator_invite_code(code: str) -> str:
    normalized = code.strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


async def _load_active_invite(
    *,
    operator_invite_repository: OperatorInviteCodeRepository,
    code: str,
) -> OperatorInviteCodeRecord:
    normalized_code = code.strip()
    if not normalized_code.startswith(OPERATOR_INVITE_PREFIX):
        raise OperatorInviteCodeError("Код приглашения не распознан.")
    invite = await operator_invite_repository.get_by_code_hash(
        code_hash=hash_operator_invite_code(normalized_code)
    )
    if invite is None:
        raise OperatorInviteCodeError("Код приглашения не найден.")
    if not invite.is_active or invite.used_count >= invite.max_uses:
        raise OperatorInviteCodeError("Код приглашения уже закрыт.")
    if invite.expires_at <= datetime.now(UTC):
        raise OperatorInviteCodeError("Срок действия приглашения закончился.")
    return invite
