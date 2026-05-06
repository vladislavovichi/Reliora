from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.filters.command import CommandObject

from application.contracts.actors import OperatorIdentity
from application.use_cases.tickets.operator_invites import (
    OperatorInviteCodePreview,
    OperatorInviteCodeRedemptionResult,
)
from application.use_cases.tickets.summaries import OperatorRoleMutationResult, OperatorSummary
from backend.grpc.contracts import HelpdeskBackendClientFactory
from bot.handlers.common.system import handle_start
from bot.handlers.user.operator_invites import handle_operator_invite_confirm
from bot.texts.operator_invites import INVITE_ONBOARDING_CONFIRMED_TEXT
from domain.enums.roles import UserRole
from tests.support.aiogram import (
    CallbackHarness,
    MessageHarness,
    build_callback_harness,
    build_message_harness,
)
from tests.support.backend import FakeHelpdeskBackendClient, build_backend_client_factory


class OperatorInviteBackendClient(FakeHelpdeskBackendClient):
    def __init__(self) -> None:
        self.preview_operator_invite_mock = AsyncMock()
        self.redeem_operator_invite_mock = AsyncMock()

    async def preview_operator_invite(self, *, code: str) -> OperatorInviteCodePreview:
        await self.preview_operator_invite_mock(code=code)
        return OperatorInviteCodePreview(
            expires_at=datetime(2026, 4, 15, 12, 0, tzinfo=UTC),
            remaining_uses=1,
        )

    async def redeem_operator_invite(
        self,
        *,
        code: str,
        operator: OperatorIdentity,
    ) -> OperatorInviteCodeRedemptionResult:
        await self.redeem_operator_invite_mock(code=code, operator=operator)
        return OperatorInviteCodeRedemptionResult(
            operator=OperatorRoleMutationResult(
                operator=OperatorSummary(
                    telegram_user_id=operator.telegram_user_id,
                    display_name="Анна Смирнова",
                    username=operator.username,
                    is_active=True,
                ),
                changed=True,
            ),
            expires_at=datetime(2026, 4, 15, 12, 0, tzinfo=UTC),
        )


def _build_helpdesk_backend_client_factory(
    service: FakeHelpdeskBackendClient,
) -> HelpdeskBackendClientFactory:
    return build_backend_client_factory(service)


def _build_message() -> MessageHarness:
    return build_message_harness(
        user_id=3001,
        message_id=10,
        text="/start opr_test",
        with_edit_text=True,
    )


def _build_callback() -> CallbackHarness:
    return build_callback_harness(
        user_id=3001,
        data="operator_invite:confirm",
        message=_build_message(),
    )


async def test_handle_start_with_invite_code_opens_onboarding_prompt() -> None:
    message = _build_message()
    state = SimpleNamespace(
        set_state=AsyncMock(),
        update_data=AsyncMock(),
    )
    service = OperatorInviteBackendClient()

    await handle_start(
        message=message.message,
        command=CommandObject(prefix="/", command="start", mention=None, args="opr_test"),
        state=state,
        helpdesk_backend_client_factory=_build_helpdesk_backend_client_factory(service),
        settings=SimpleNamespace(
            mini_app=SimpleNamespace(
                telegram_launch_url=None,
                public_url_is_valid=False,
            )
        ),
        event_user_role=UserRole.USER,
    )

    state.set_state.assert_awaited()
    message.answer.assert_awaited_once()
    assert message.answer.await_args is not None
    assert "Приглашение оператора подтверждено." in message.answer.await_args.args[0]


async def test_handle_operator_invite_confirm_redeems_invite_and_opens_operator_menu() -> None:
    callback = _build_callback()
    state = SimpleNamespace(
        get_data=AsyncMock(
            return_value={
                "operator_invite_code": "opr_test",
                "operator_invite_display_name": "Анна Смирнова",
            }
        ),
        clear=AsyncMock(),
    )
    service = OperatorInviteBackendClient()

    await handle_operator_invite_confirm(
        callback=callback.callback,
        state=state,
        helpdesk_backend_client_factory=_build_helpdesk_backend_client_factory(service),
        settings=SimpleNamespace(
            mini_app=SimpleNamespace(
                telegram_launch_url=None,
                public_url_is_valid=False,
            )
        ),
    )

    callback.answer.assert_awaited_once_with(INVITE_ONBOARDING_CONFIRMED_TEXT)
    assert callback.message.edit_text is not None
    callback.message.edit_text.assert_awaited_once()
    callback.message.answer.assert_awaited_once()
    assert callback.message.answer.await_args is not None
    reply_markup = callback.message.answer.await_args.kwargs["reply_markup"]
    assert reply_markup.keyboard[0][0].text == "Очередь"
