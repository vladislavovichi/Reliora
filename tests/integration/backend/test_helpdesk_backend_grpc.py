from __future__ import annotations

import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest

from application.ai.summaries import (
    AIPredictionConfidence,
    TicketAssistSnapshot,
    TicketCategoryPrediction,
    TicketMacroSuggestion,
    TicketReplyDraft,
    TicketSummaryStatus,
)
from application.contracts.actors import OperatorIdentity, RequestActor
from application.contracts.ai import PredictTicketCategoryCommand
from application.contracts.tickets import AddInternalNoteCommand, ClientTicketMessageCommand
from application.errors import ForbiddenError
from application.services.helpdesk.service import HelpdeskService, HelpdeskServiceFactory
from application.services.stats import (
    AnalyticsCategorySnapshot,
    AnalyticsOperatorSnapshot,
    AnalyticsRatingBucket,
    AnalyticsWindow,
    HelpdeskAnalyticsSnapshot,
    OperatorTicketLoad,
)
from application.use_cases.tickets.operator_invites import (
    OperatorInviteCodePreview,
    OperatorInviteCodeRedemptionResult,
    OperatorInviteCodeSummary,
)
from application.use_cases.tickets.summaries import (
    HistoricalTicketSummary,
    MacroSummary,
    OperatorRoleMutationResult,
    OperatorSummary,
    TagSummary,
    TicketCategorySummary,
    TicketFeedbackMutationResult,
    TicketFeedbackMutationStatus,
    TicketFeedbackSummary,
    TicketSummary,
    TicketTagMutationResult,
    TicketTagsSummary,
)
from backend.grpc.client import build_helpdesk_backend_client_factory
from backend.grpc.server import build_helpdesk_backend_server
from domain.entities.ticket import TicketAttachmentDetails
from domain.enums.roles import UserRole
from domain.enums.tickets import TicketAttachmentKind, TicketStatus
from infrastructure.config.settings import BackendAuthConfig, BackendServiceConfig, ResilienceConfig


@asynccontextmanager
async def _build_service_factory(service: object) -> AsyncIterator[HelpdeskService]:
    yield cast(HelpdeskService, service)


async def test_helpdesk_grpc_client_roundtrips_ticket_commands_and_analytics() -> None:
    ticket_public_id = uuid4()
    command_log: list[ClientTicketMessageCommand] = []
    service = SimpleNamespace(
        get_access_context=_build_access_context_call(),
        create_ticket_from_client_intake=_capture_create_call(command_log, ticket_public_id),
        get_ticket_ai_assist_snapshot=_build_ticket_assist_call(),
        generate_ticket_reply_draft=_build_reply_draft_call(),
        predict_ticket_category=_build_category_prediction_call(),
        get_analytics_snapshot=_build_analytics_call(),
        list_archived_tickets=_build_archived_tickets_call(ticket_public_id),
        list_operators=_build_operators_call(),
        create_operator_invite=_build_operator_invite_call(),
        preview_operator_invite=_build_operator_invite_preview_call(),
        redeem_operator_invite=_build_operator_invite_redemption_call(),
        promote_operator=_build_promote_operator_call(),
        revoke_operator=_build_revoke_operator_call(),
        list_macros=_build_macros_call(),
        get_macro=_build_get_macro_call(),
        create_macro=_build_create_macro_call(),
        update_macro_title=_build_update_macro_title_call(),
        update_macro_body=_build_update_macro_body_call(),
        delete_macro=_build_delete_macro_call(),
        list_ticket_categories=_build_ticket_categories_call(),
        get_ticket_category=_build_get_ticket_category_call(),
        create_ticket_category=_build_create_ticket_category_call(),
        update_ticket_category_title=_build_update_ticket_category_title_call(),
        set_ticket_category_active=_build_set_ticket_category_active_call(),
        list_ticket_tags=_build_ticket_tags_call(ticket_public_id),
        list_available_tags=_build_available_tags_call(),
        add_tag_to_ticket=_build_add_tag_call(ticket_public_id),
        remove_tag_from_ticket=_build_remove_tag_call(ticket_public_id),
        submit_ticket_feedback_rating=_build_feedback_rating_call(ticket_public_id),
        get_ticket_feedback=_build_get_feedback_call(ticket_public_id),
        add_ticket_feedback_comment=_build_feedback_comment_call(ticket_public_id),
        escalate_ticket_as_operator=_build_escalate_call(ticket_public_id),
        add_internal_note_to_ticket=_build_add_note_call(ticket_public_id),
    )
    helpdesk_service_factory = cast(
        HelpdeskServiceFactory,
        lambda: _build_service_factory(service),
    )
    port = _reserve_tcp_port()
    server = build_helpdesk_backend_server(
        helpdesk_service_factory=helpdesk_service_factory,
        bind_target=f"127.0.0.1:{port}",
        auth_config=BackendAuthConfig(token="internal-test-token", caller="test-client"),
    )
    await server.start()

    client_factory = build_helpdesk_backend_client_factory(
        BackendServiceConfig(host="127.0.0.1", port=port),
        auth_config=BackendAuthConfig(token="internal-test-token", caller="test-client"),
        resilience_config=ResilienceConfig(),
    )

    try:
        async with client_factory() as client:
            service_name, status = await client.get_backend_status()
            access_context = await client.get_access_context(
                actor=RequestActor(telegram_user_id=42)
            )
            ticket = await client.create_ticket_from_client_intake(
                ClientTicketMessageCommand(
                    client_chat_id=2002,
                    telegram_message_id=15,
                    text="Не открывается доступ",
                    attachment=TicketAttachmentDetails(
                        kind=TicketAttachmentKind.DOCUMENT,
                        telegram_file_id="file-1",
                        telegram_file_unique_id="unique-1",
                        filename="issue.txt",
                        mime_type="text/plain",
                        storage_path="document/unique-1.txt",
                    ),
                    category_id=2,
                )
            )
            snapshot = await client.get_analytics_snapshot(
                window=AnalyticsWindow.DAYS_7,
                actor=RequestActor(telegram_user_id=1001),
            )
            ticket_assist = await client.get_ticket_ai_assist_snapshot(
                ticket_public_id=ticket_public_id,
                refresh_summary=True,
                actor=RequestActor(telegram_user_id=1001),
            )
            reply_draft = await client.generate_ticket_reply_draft(
                ticket_public_id=ticket_public_id,
                actor=RequestActor(telegram_user_id=1001),
            )
            category_prediction = await client.predict_ticket_category(
                PredictTicketCategoryCommand(text="Не удаётся войти после смены пароля"),
                actor=RequestActor(telegram_user_id=2002),
            )
            archived_tickets = await client.list_archived_tickets(
                actor=RequestActor(telegram_user_id=1001),
            )
            operators = await client.list_operators(actor=RequestActor(telegram_user_id=42))
            invite = await client.create_operator_invite(actor=RequestActor(telegram_user_id=42))
            invite_preview = await client.preview_operator_invite(code="opr_test")
            invite_redemption = await client.redeem_operator_invite(
                code="opr_test",
                operator=OperatorIdentity(
                    telegram_user_id=3001,
                    display_name="New Operator",
                    username="new.operator",
                ),
            )
            promoted = await client.promote_operator(
                OperatorIdentity(
                    telegram_user_id=3002,
                    display_name="Promoted Operator",
                    username=None,
                ),
                actor=RequestActor(telegram_user_id=42),
            )
            revoked = await client.revoke_operator(
                telegram_user_id=3002,
                actor=RequestActor(telegram_user_id=42),
            )
            macros = await client.list_macros(actor=RequestActor(telegram_user_id=42))
            macro = await client.get_macro(macro_id=11, actor=RequestActor(telegram_user_id=42))
            created_macro = await client.create_macro(
                title="Greeting",
                body="Hello",
                actor=RequestActor(telegram_user_id=42),
            )
            updated_macro_title = await client.update_macro_title(
                macro_id=11,
                title="Updated",
                actor=RequestActor(telegram_user_id=42),
            )
            updated_macro_body = await client.update_macro_body(
                macro_id=11,
                body="Updated body",
                actor=RequestActor(telegram_user_id=42),
            )
            deleted_macro = await client.delete_macro(
                macro_id=11,
                actor=RequestActor(telegram_user_id=42),
            )
            categories = await client.list_ticket_categories(
                actor=RequestActor(telegram_user_id=42),
            )
            category = await client.get_ticket_category(
                category_id=2,
                actor=RequestActor(telegram_user_id=42),
            )
            created_category = await client.create_ticket_category(
                title="Access",
                actor=RequestActor(telegram_user_id=42),
            )
            updated_category = await client.update_ticket_category_title(
                category_id=2,
                title="Access updated",
                actor=RequestActor(telegram_user_id=42),
            )
            toggled_category = await client.set_ticket_category_active(
                category_id=2,
                is_active=False,
                actor=RequestActor(telegram_user_id=42),
            )
            ticket_tags = await client.list_ticket_tags(
                ticket_public_id=ticket_public_id,
                actor=RequestActor(telegram_user_id=42),
            )
            available_tags = await client.list_available_tags(
                actor=RequestActor(telegram_user_id=42)
            )
            added_tag = await client.add_tag_to_ticket(
                ticket_public_id=ticket_public_id,
                tag_name="vip",
                actor=RequestActor(telegram_user_id=42),
            )
            removed_tag = await client.remove_tag_from_ticket(
                ticket_public_id=ticket_public_id,
                tag_name="vip",
                actor=RequestActor(telegram_user_id=42),
            )
            feedback_rating = await client.submit_ticket_feedback_rating(
                ticket_public_id=ticket_public_id,
                client_chat_id=2002,
                rating=5,
            )
            feedback = await client.get_ticket_feedback(ticket_public_id=ticket_public_id)
            feedback_comment = await client.add_ticket_feedback_comment(
                ticket_public_id=ticket_public_id,
                client_chat_id=2002,
                comment="Спасибо",
            )
            escalated_ticket = await client.escalate_ticket_as_operator(
                ticket_public_id=ticket_public_id,
                actor=RequestActor(telegram_user_id=1001),
            )
            noted_ticket = await client.add_internal_note_to_ticket(
                AddInternalNoteCommand(
                    ticket_public_id=ticket_public_id,
                    author=OperatorIdentity(
                        telegram_user_id=1001,
                        display_name="Operator One",
                        username="operator.one",
                    ),
                    text="Проверили историю и подготовили следующее действие.",
                ),
                actor=RequestActor(telegram_user_id=1001),
            )
    finally:
        await server.stop()

    assert service_name == "helpdesk-backend"
    assert status == "ready"
    assert access_context.role is UserRole.SUPER_ADMIN
    assert ticket.public_id == ticket_public_id
    assert ticket.status == TicketStatus.QUEUED
    assert command_log[0].attachment is not None
    assert command_log[0].attachment.storage_path == "document/unique-1.txt"
    assert command_log[0].category_id == 2
    assert snapshot.window == AnalyticsWindow.DAYS_7
    assert snapshot.feedback_count == 4
    assert ticket_assist is not None
    assert ticket_assist.short_summary == "Клиент потерял доступ после смены пароля."
    assert ticket_assist.summary_status is TicketSummaryStatus.FRESH
    assert ticket_assist.macro_suggestions[0].macro_id == 11
    assert reply_draft is not None
    assert reply_draft.reply_text == "Здравствуйте! Проверим заявку и вернёмся с ответом."
    assert reply_draft.confidence == 0.8
    assert category_prediction.category_id == 2
    assert category_prediction.confidence == AIPredictionConfidence.HIGH
    assert archived_tickets[0].public_id == ticket_public_id
    assert archived_tickets[0].mini_title == "Не могу войти в кабинет после обновления пароля"
    assert operators[0].display_name == "Operator One"
    assert invite.code.startswith("opr_")
    assert invite_preview.remaining_uses == 1
    assert invite_redemption.operator.operator.telegram_user_id == 3001
    assert promoted.changed is True
    assert revoked is not None
    assert revoked.operator.telegram_user_id == 3002
    assert macros[0].title == "Password reset"
    assert macro is not None
    assert macro.id == 11
    assert created_macro.title == "Greeting"
    assert updated_macro_title is not None
    assert updated_macro_title.title == "Updated"
    assert updated_macro_body is not None
    assert updated_macro_body.body == "Updated body"
    assert deleted_macro is not None
    assert deleted_macro.id == 11
    assert categories[0].title == "Access"
    assert category is not None
    assert category.id == 2
    assert created_category.title == "Access"
    assert updated_category is not None
    assert updated_category.title == "Access updated"
    assert toggled_category is not None
    assert toggled_category.is_active is False
    assert ticket_tags is not None
    assert ticket_tags.tags == ("vip",)
    assert available_tags[0].name == "vip"
    assert added_tag is not None
    assert added_tag.changed is True
    assert removed_tag is not None
    assert removed_tag.changed is True
    assert feedback_rating.status is TicketFeedbackMutationStatus.CREATED
    assert feedback is not None
    assert feedback.rating == 5
    assert feedback_comment.status is TicketFeedbackMutationStatus.UPDATED
    assert escalated_ticket is not None
    assert escalated_ticket.status is TicketStatus.ESCALATED
    assert noted_ticket is not None
    assert noted_ticket.public_id == ticket_public_id


async def test_helpdesk_grpc_rejects_invalid_internal_token() -> None:
    helpdesk_service_factory = cast(
        HelpdeskServiceFactory,
        lambda: _build_service_factory(SimpleNamespace()),
    )
    port = _reserve_tcp_port()
    server = build_helpdesk_backend_server(
        helpdesk_service_factory=helpdesk_service_factory,
        bind_target=f"127.0.0.1:{port}",
        auth_config=BackendAuthConfig(token="expected-token", caller="test-client"),
    )
    await server.start()

    client_factory = build_helpdesk_backend_client_factory(
        BackendServiceConfig(host="127.0.0.1", port=port),
        auth_config=BackendAuthConfig(token="wrong-token", caller="test-client"),
        resilience_config=ResilienceConfig(),
    )

    try:
        async with client_factory() as client:
            try:
                await client.get_backend_status()
            except ForbiddenError as exc:
                assert "отклонён" in str(exc)
            else:
                raise AssertionError("expected ForbiddenError")
    finally:
        await server.stop()


def _capture_create_call(
    command_log: list[ClientTicketMessageCommand],
    ticket_public_id: Any,
) -> Any:
    async def call(command: ClientTicketMessageCommand) -> TicketSummary:
        command_log.append(command)
        return TicketSummary(
            public_id=ticket_public_id,
            public_number="HD-AAAA1111",
            status=TicketStatus.QUEUED,
            created=True,
        )

    return call


def _build_access_context_call() -> Any:
    async def call(*, actor: RequestActor | None) -> Any:
        assert actor == RequestActor(telegram_user_id=42)
        return SimpleNamespace(
            telegram_user_id=42,
            role=UserRole.SUPER_ADMIN,
        )

    return call


def _build_analytics_call() -> Any:
    async def call(
        *,
        window: AnalyticsWindow,
        actor: RequestActor | None = None,
    ) -> HelpdeskAnalyticsSnapshot:
        assert actor == RequestActor(telegram_user_id=1001)
        return HelpdeskAnalyticsSnapshot(
            window=window,
            total_open_tickets=6,
            queued_tickets_count=2,
            assigned_tickets_count=3,
            escalated_tickets_count=1,
            closed_tickets_count=4,
            tickets_per_operator=(
                OperatorTicketLoad(operator_id=7, display_name="Operator One", ticket_count=3),
            ),
            period_created_tickets_count=9,
            period_closed_tickets_count=5,
            average_first_response_time_seconds=126,
            average_resolution_time_seconds=7260,
            satisfaction_average=4.7,
            feedback_count=4,
            feedback_coverage_percent=80,
            rating_distribution=(AnalyticsRatingBucket(rating=5, count=3),),
            operator_snapshots=(
                AnalyticsOperatorSnapshot(
                    operator_id=7,
                    display_name="Operator One",
                    active_ticket_count=3,
                    closed_ticket_count=4,
                    average_first_response_time_seconds=120,
                    average_resolution_time_seconds=5400,
                    average_satisfaction=4.8,
                    feedback_count=3,
                ),
            ),
            category_snapshots=(
                AnalyticsCategorySnapshot(
                    category_id=1,
                    category_title="Доступ и вход",
                    created_ticket_count=5,
                    open_ticket_count=2,
                    closed_ticket_count=3,
                    average_satisfaction=4.5,
                    feedback_count=2,
                    sla_breach_count=2,
                ),
            ),
            best_operators_by_closures=(),
            best_operators_by_satisfaction=(),
            top_categories=(),
            first_response_breach_count=2,
            resolution_breach_count=1,
            sla_categories=(),
        )

    return call


def _build_ticket_assist_call() -> Any:
    async def call(
        *,
        ticket_public_id: Any,
        refresh_summary: bool = False,
        actor: RequestActor | None = None,
    ) -> TicketAssistSnapshot:
        assert actor == RequestActor(telegram_user_id=1001)
        assert ticket_public_id is not None
        assert refresh_summary is True
        return TicketAssistSnapshot(
            available=True,
            summary_status=TicketSummaryStatus.FRESH,
            short_summary="Клиент потерял доступ после смены пароля.",
            user_goal="Хочет быстро восстановить вход без новой регистрации.",
            actions_taken="Оператор проверил карточку профиля и подготовил сброс доступа.",
            current_status="Ожидается подтверждение входа после обновления ссылки.",
            macro_suggestions=(
                TicketMacroSuggestion(
                    macro_id=11,
                    title="Сброс доступа",
                    body="Сбросили пароль и обновили ссылку.",
                    reason="Подходит под типовой сценарий восстановления входа.",
                    confidence=AIPredictionConfidence.HIGH,
                ),
            ),
            model_id="Qwen/Qwen3.5-4B",
        )

    return call


def _build_reply_draft_call() -> Any:
    async def call(
        *,
        ticket_public_id: Any,
        actor: RequestActor | None = None,
    ) -> TicketReplyDraft:
        assert actor == RequestActor(telegram_user_id=1001)
        assert ticket_public_id is not None
        return TicketReplyDraft(
            available=True,
            reply_text="Здравствуйте! Проверим заявку и вернёмся с ответом.",
            tone="polite",
            confidence=0.8,
            safety_note="Без обещаний сроков.",
            missing_information=("номер заказа",),
            model_id="reply-model",
        )

    return call


def _build_category_prediction_call() -> Any:
    async def call(
        command: PredictTicketCategoryCommand,
        *,
        actor: RequestActor | None = None,
    ) -> TicketCategoryPrediction:
        assert actor == RequestActor(telegram_user_id=2002)
        assert command.text == "Не удаётся войти после смены пароля"
        return TicketCategoryPrediction(
            available=True,
            category_id=2,
            category_code="access",
            category_title="Доступ и вход",
            confidence=AIPredictionConfidence.HIGH,
            reason="В тексте явный запрос на восстановление доступа.",
            model_id="Qwen/Qwen3.5-4B",
        )

    return call


def _build_archived_tickets_call(ticket_public_id: Any) -> Any:
    async def call(
        *,
        limit: int | None = None,
        offset: int = 0,
        actor: RequestActor | None = None,
    ) -> tuple[HistoricalTicketSummary, ...]:
        assert actor == RequestActor(telegram_user_id=1001)
        assert limit is None
        assert offset == 0
        return (
            HistoricalTicketSummary(
                public_id=ticket_public_id,
                public_number="HD-AAAA1111",
                status=TicketStatus.CLOSED,
                created_at=datetime(2026, 4, 7, 9, 0, tzinfo=UTC),
                closed_at=datetime(2026, 4, 7, 11, 45, tzinfo=UTC),
                mini_title="Не могу войти в кабинет после обновления пароля",
                category_id=2,
                category_code="access",
                category_title="Доступ и вход",
            ),
        )

    return call


def _build_operators_call() -> Any:
    async def call(
        *,
        actor: RequestActor | None = None,
    ) -> tuple[OperatorSummary, ...]:
        assert actor == RequestActor(telegram_user_id=42)
        return (
            OperatorSummary(
                telegram_user_id=1001,
                display_name="Operator One",
                username="operator.one",
                is_active=True,
            ),
        )

    return call


def _operator_summary(
    *,
    telegram_user_id: int,
    display_name: str,
) -> OperatorSummary:
    return OperatorSummary(
        telegram_user_id=telegram_user_id,
        display_name=display_name,
        username=None,
        is_active=True,
    )


def _build_operator_invite_call() -> Any:
    async def call(
        *,
        actor: RequestActor | None = None,
    ) -> OperatorInviteCodeSummary:
        assert actor == RequestActor(telegram_user_id=42)
        return OperatorInviteCodeSummary(
            code="opr_test_invite",
            expires_at=datetime(2026, 4, 17, 12, 0, tzinfo=UTC),
            max_uses=1,
        )

    return call


def _build_operator_invite_preview_call() -> Any:
    async def call(*, code: str) -> OperatorInviteCodePreview:
        assert code == "opr_test"
        return OperatorInviteCodePreview(
            expires_at=datetime(2026, 4, 17, 12, 0, tzinfo=UTC),
            remaining_uses=1,
        )

    return call


def _build_operator_invite_redemption_call() -> Any:
    async def call(
        *,
        code: str,
        operator: OperatorIdentity,
    ) -> OperatorInviteCodeRedemptionResult:
        assert code == "opr_test"
        return OperatorInviteCodeRedemptionResult(
            operator=OperatorRoleMutationResult(
                operator=OperatorSummary(
                    telegram_user_id=operator.telegram_user_id,
                    display_name=operator.display_name,
                    username=operator.username,
                    is_active=True,
                ),
                changed=True,
            ),
            expires_at=datetime(2026, 4, 17, 12, 0, tzinfo=UTC),
        )

    return call


def _build_promote_operator_call() -> Any:
    async def call(
        operator: OperatorIdentity,
        actor: RequestActor | None = None,
    ) -> OperatorRoleMutationResult:
        assert actor == RequestActor(telegram_user_id=42)
        return OperatorRoleMutationResult(
            operator=OperatorSummary(
                telegram_user_id=operator.telegram_user_id,
                display_name=operator.display_name,
                username=operator.username,
                is_active=True,
            ),
            changed=True,
        )

    return call


def _build_revoke_operator_call() -> Any:
    async def call(
        *,
        telegram_user_id: int,
        actor: RequestActor | None = None,
    ) -> OperatorRoleMutationResult:
        assert actor == RequestActor(telegram_user_id=42)
        return OperatorRoleMutationResult(
            operator=_operator_summary(
                telegram_user_id=telegram_user_id,
                display_name="Promoted Operator",
            ),
            changed=True,
        )

    return call


def _macro_summary(*, title: str = "Password reset", body: str = "Reset body") -> MacroSummary:
    return MacroSummary(id=11, title=title, body=body)


def _build_macros_call() -> Any:
    async def call(*, actor: RequestActor | None = None) -> tuple[MacroSummary, ...]:
        assert actor == RequestActor(telegram_user_id=42)
        return (_macro_summary(),)

    return call


def _build_get_macro_call() -> Any:
    async def call(
        *,
        macro_id: int,
        actor: RequestActor | None = None,
    ) -> MacroSummary | None:
        assert actor == RequestActor(telegram_user_id=42)
        return _macro_summary() if macro_id == 11 else None

    return call


def _build_create_macro_call() -> Any:
    async def call(
        *,
        title: str,
        body: str,
        actor: RequestActor | None = None,
    ) -> MacroSummary:
        assert actor == RequestActor(telegram_user_id=42)
        return _macro_summary(title=title, body=body)

    return call


def _build_update_macro_title_call() -> Any:
    async def call(
        *,
        macro_id: int,
        title: str,
        actor: RequestActor | None = None,
    ) -> MacroSummary | None:
        assert macro_id == 11
        assert actor == RequestActor(telegram_user_id=42)
        return _macro_summary(title=title)

    return call


def _build_update_macro_body_call() -> Any:
    async def call(
        *,
        macro_id: int,
        body: str,
        actor: RequestActor | None = None,
    ) -> MacroSummary | None:
        assert macro_id == 11
        assert actor == RequestActor(telegram_user_id=42)
        return _macro_summary(body=body)

    return call


def _build_delete_macro_call() -> Any:
    async def call(
        *,
        macro_id: int,
        actor: RequestActor | None = None,
    ) -> MacroSummary | None:
        assert actor == RequestActor(telegram_user_id=42)
        return _macro_summary() if macro_id == 11 else None

    return call


def _category_summary(
    *,
    title: str = "Access",
    is_active: bool = True,
) -> TicketCategorySummary:
    return TicketCategorySummary(
        id=2,
        code="access",
        title=title,
        is_active=is_active,
        sort_order=20,
    )


def _build_ticket_categories_call() -> Any:
    async def call(*, actor: RequestActor | None = None) -> tuple[TicketCategorySummary, ...]:
        assert actor == RequestActor(telegram_user_id=42)
        return (_category_summary(),)

    return call


def _build_get_ticket_category_call() -> Any:
    async def call(
        *,
        category_id: int,
        actor: RequestActor | None = None,
    ) -> TicketCategorySummary | None:
        assert actor == RequestActor(telegram_user_id=42)
        return _category_summary() if category_id == 2 else None

    return call


def _build_create_ticket_category_call() -> Any:
    async def call(
        *,
        title: str,
        actor: RequestActor | None = None,
    ) -> TicketCategorySummary:
        assert actor == RequestActor(telegram_user_id=42)
        return _category_summary(title=title)

    return call


def _build_update_ticket_category_title_call() -> Any:
    async def call(
        *,
        category_id: int,
        title: str,
        actor: RequestActor | None = None,
    ) -> TicketCategorySummary | None:
        assert category_id == 2
        assert actor == RequestActor(telegram_user_id=42)
        return _category_summary(title=title)

    return call


def _build_set_ticket_category_active_call() -> Any:
    async def call(
        *,
        category_id: int,
        is_active: bool,
        actor: RequestActor | None = None,
    ) -> TicketCategorySummary | None:
        assert category_id == 2
        assert actor == RequestActor(telegram_user_id=42)
        return _category_summary(is_active=is_active)

    return call


def _build_ticket_tags_call(ticket_public_id: Any) -> Any:
    async def call(
        *,
        ticket_public_id: Any,
        actor: RequestActor | None = None,
    ) -> TicketTagsSummary | None:
        assert actor == RequestActor(telegram_user_id=42)
        return TicketTagsSummary(
            public_id=ticket_public_id,
            public_number="HD-AAAA1111",
            tags=("vip",),
        )

    return call


def _build_available_tags_call() -> Any:
    async def call(*, actor: RequestActor | None = None) -> tuple[TagSummary, ...]:
        assert actor == RequestActor(telegram_user_id=42)
        return (TagSummary(id=1, name="vip"),)

    return call


def _build_add_tag_call(ticket_public_id: Any) -> Any:
    async def call(
        *,
        ticket_public_id: Any,
        tag_name: str,
        actor: RequestActor | None = None,
    ) -> TicketTagMutationResult | None:
        assert actor == RequestActor(telegram_user_id=42)
        return TicketTagMutationResult(
            ticket=TicketSummary(
                public_id=ticket_public_id,
                public_number="HD-AAAA1111",
                status=TicketStatus.ASSIGNED,
            ),
            tag=tag_name,
            changed=True,
            tags=(tag_name,),
        )

    return call


def _build_remove_tag_call(ticket_public_id: Any) -> Any:
    async def call(
        *,
        ticket_public_id: Any,
        tag_name: str,
        actor: RequestActor | None = None,
    ) -> TicketTagMutationResult | None:
        assert actor == RequestActor(telegram_user_id=42)
        return TicketTagMutationResult(
            ticket=TicketSummary(
                public_id=ticket_public_id,
                public_number="HD-AAAA1111",
                status=TicketStatus.ASSIGNED,
            ),
            tag=tag_name,
            changed=True,
            tags=(),
        )

    return call


def _feedback_summary(
    ticket_public_id: Any,
    *,
    comment: str | None = None,
) -> TicketFeedbackSummary:
    return TicketFeedbackSummary(
        public_id=ticket_public_id,
        public_number="HD-AAAA1111",
        client_chat_id=2002,
        rating=5,
        comment=comment,
        submitted_at=datetime(2026, 4, 8, 12, 30, tzinfo=UTC),
    )


def _build_feedback_rating_call(ticket_public_id: Any) -> Any:
    async def call(
        *,
        ticket_public_id: Any,
        client_chat_id: int,
        rating: int,
    ) -> TicketFeedbackMutationResult:
        assert client_chat_id == 2002
        assert rating == 5
        return TicketFeedbackMutationResult(
            status=TicketFeedbackMutationStatus.CREATED,
            feedback=_feedback_summary(ticket_public_id),
        )

    return call


def _build_get_feedback_call(ticket_public_id: Any) -> Any:
    async def call(*, ticket_public_id: Any) -> TicketFeedbackSummary | None:
        return _feedback_summary(ticket_public_id)

    return call


def _build_feedback_comment_call(ticket_public_id: Any) -> Any:
    async def call(
        *,
        ticket_public_id: Any,
        client_chat_id: int,
        comment: str,
    ) -> TicketFeedbackMutationResult:
        assert client_chat_id == 2002
        return TicketFeedbackMutationResult(
            status=TicketFeedbackMutationStatus.UPDATED,
            feedback=_feedback_summary(ticket_public_id, comment=comment),
        )

    return call


def _build_escalate_call(ticket_public_id: Any) -> Any:
    async def call(
        *,
        ticket_public_id: Any,
        actor: RequestActor | None = None,
    ) -> TicketSummary:
        assert actor == RequestActor(telegram_user_id=1001)
        return TicketSummary(
            public_id=ticket_public_id,
            public_number="HD-AAAA1111",
            status=TicketStatus.ESCALATED,
        )

    return call


def _build_add_note_call(ticket_public_id: Any) -> Any:
    async def call(
        command: AddInternalNoteCommand,
        *,
        actor: RequestActor | None = None,
    ) -> TicketSummary:
        assert actor == RequestActor(telegram_user_id=1001)
        assert command.text == "Проверили историю и подготовили следующее действие."
        return TicketSummary(
            public_id=ticket_public_id,
            public_number="HD-AAAA1111",
            status=TicketStatus.ASSIGNED,
        )

    return call


def _reserve_tcp_port() -> int:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            return cast(int, sock.getsockname()[1])
    except PermissionError as exc:
        pytest.skip(f"Sandbox blocks local TCP sockets: {exc}")
