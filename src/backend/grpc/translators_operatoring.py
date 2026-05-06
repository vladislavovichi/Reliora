# mypy: disable-error-code="attr-defined,name-defined"
from __future__ import annotations

from application.use_cases.tickets.operator_invites import (
    OperatorInviteCodePreview,
    OperatorInviteCodeRedemptionResult,
    OperatorInviteCodeSummary,
)
from application.use_cases.tickets.summaries import (
    AccessContextSummary,
    OperatorRoleMutationResult,
    OperatorSummary,
)
from backend.grpc.generated import helpdesk_pb2
from backend.grpc.translators_shared import _deserialize_timestamp, _has, _serialize_timestamp
from domain.enums.roles import UserRole


def serialize_access_context(
    access_context: AccessContextSummary,
) -> helpdesk_pb2.AccessContextSummary:
    return helpdesk_pb2.AccessContextSummary(
        telegram_user_id=access_context.telegram_user_id,
        role=access_context.role.value,
    )


def deserialize_access_context(
    access_context: helpdesk_pb2.AccessContextSummary,
) -> AccessContextSummary:
    return AccessContextSummary(
        telegram_user_id=access_context.telegram_user_id,
        role=UserRole(access_context.role),
    )


def serialize_operator_summary(operator: OperatorSummary) -> helpdesk_pb2.OperatorSummary:
    message = helpdesk_pb2.OperatorSummary(
        telegram_user_id=operator.telegram_user_id,
        display_name=operator.display_name,
        is_active=operator.is_active,
    )
    if operator.username is not None:
        message.username = operator.username
    return message


def deserialize_operator_summary(
    operator: helpdesk_pb2.OperatorSummary,
) -> OperatorSummary:
    return OperatorSummary(
        telegram_user_id=operator.telegram_user_id,
        display_name=operator.display_name,
        username=operator.username if _has(operator, "username") else None,
        is_active=operator.is_active,
    )


def serialize_operator_role_mutation_result(
    result: OperatorRoleMutationResult,
) -> helpdesk_pb2.OperatorRoleMutationResult:
    message = helpdesk_pb2.OperatorRoleMutationResult(changed=result.changed)
    message.operator.CopyFrom(serialize_operator_summary(result.operator))
    return message


def deserialize_operator_role_mutation_result(
    result: helpdesk_pb2.OperatorRoleMutationResult,
) -> OperatorRoleMutationResult:
    return OperatorRoleMutationResult(
        operator=deserialize_operator_summary(result.operator),
        changed=result.changed,
    )


def serialize_operator_invite_summary(
    invite: OperatorInviteCodeSummary,
) -> helpdesk_pb2.OperatorInviteCodeSummary:
    return helpdesk_pb2.OperatorInviteCodeSummary(
        code=invite.code,
        expires_at=_serialize_timestamp(invite.expires_at),
        max_uses=invite.max_uses,
    )


def serialize_operator_invite_preview(
    invite: OperatorInviteCodePreview,
) -> helpdesk_pb2.OperatorInviteCodePreview:
    return helpdesk_pb2.OperatorInviteCodePreview(
        expires_at=_serialize_timestamp(invite.expires_at),
        remaining_uses=invite.remaining_uses,
    )


def deserialize_operator_invite_preview(
    invite: helpdesk_pb2.OperatorInviteCodePreview,
) -> OperatorInviteCodePreview:
    return OperatorInviteCodePreview(
        expires_at=_deserialize_timestamp(invite.expires_at),
        remaining_uses=invite.remaining_uses,
    )


def serialize_operator_invite_redemption_result(
    result: OperatorInviteCodeRedemptionResult,
) -> helpdesk_pb2.OperatorInviteCodeRedemptionResult:
    message = helpdesk_pb2.OperatorInviteCodeRedemptionResult(
        expires_at=_serialize_timestamp(result.expires_at)
    )
    message.operator.CopyFrom(serialize_operator_role_mutation_result(result.operator))
    return message


def deserialize_operator_invite_redemption_result(
    result: helpdesk_pb2.OperatorInviteCodeRedemptionResult,
) -> OperatorInviteCodeRedemptionResult:
    return OperatorInviteCodeRedemptionResult(
        operator=deserialize_operator_role_mutation_result(result.operator),
        expires_at=_deserialize_timestamp(result.expires_at),
    )


def deserialize_operator_invite_summary(
    invite: helpdesk_pb2.OperatorInviteCodeSummary,
) -> OperatorInviteCodeSummary:
    return OperatorInviteCodeSummary(
        code=invite.code,
        expires_at=_deserialize_timestamp(invite.expires_at),
        max_uses=invite.max_uses,
    )
