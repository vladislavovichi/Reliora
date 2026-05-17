from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import UUID, uuid4

from application.ai.summaries import TicketAssistSnapshot, TicketSummaryStatus
from application.contracts.actors import RequestActor
from application.use_cases.tickets.summaries import (
    AccessContextSummary,
    MacroSummary,
    OperatorSummary,
    TicketDetailsSummary,
    TicketInternalNoteSummary,
    TicketMessageSummary,
)
from backend.grpc.contracts import HelpdeskBackendClientFactory
from domain.enums.roles import UserRole
from domain.enums.tickets import TicketMessageSenderType, TicketStatus
from mini_app.api import MiniAppGateway
from mini_app.auth import TelegramMiniAppUser
from mini_app.serializers import serialize_ticket_timeline
from tests.support.backend import FakeHelpdeskBackendClient, build_backend_client_factory


class TimelineBackendClient(FakeHelpdeskBackendClient):
    def __init__(
        self,
        *,
        ticket: TicketDetailsSummary | None = None,
        ai: TicketAssistSnapshot | None = None,
    ) -> None:
        self.ticket = ticket or _build_ticket()
        self.ai = ai or _build_ai_snapshot()

    async def get_access_context(self, *, actor: RequestActor) -> AccessContextSummary:
        return AccessContextSummary(telegram_user_id=actor.telegram_user_id, role=UserRole.OPERATOR)

    async def get_ticket_details(
        self,
        *,
        ticket_public_id: UUID,
        actor: RequestActor | None = None,
    ) -> TicketDetailsSummary | None:
        del ticket_public_id, actor
        return self.ticket

    async def get_ticket_ai_assist_snapshot(
        self,
        *,
        ticket_public_id: UUID,
        refresh_summary: bool = False,
        actor: RequestActor | None = None,
    ) -> TicketAssistSnapshot | None:
        del ticket_public_id, refresh_summary, actor
        return self.ai

    async def list_macros(self, *, actor: RequestActor | None = None) -> tuple[MacroSummary, ...]:
        del actor
        return ()

    async def list_operators(
        self,
        *,
        actor: RequestActor | None = None,
    ) -> tuple[OperatorSummary, ...]:
        del actor
        return ()


def build_backend_factory(client: TimelineBackendClient) -> HelpdeskBackendClientFactory:
    return build_backend_client_factory(client)


def test_ticket_timeline_serializer_orders_items_chronologically() -> None:
    timeline = serialize_ticket_timeline(_build_ticket(), _build_ai_snapshot())

    assert timeline["warning"] is None
    items = timeline["items"]
    assert [item["type"] for item in items] == [
        "ticket_created",
        "ticket_assigned",
        "message_received",
        "operator_reply",
        "internal_note_added",
        "ai_summary_generated",
        "ticket_closed",
    ]
    assert [item["created_at"] for item in items] == sorted(item["created_at"] for item in items)


def test_ticket_timeline_serializer_uses_safe_metadata() -> None:
    timeline = serialize_ticket_timeline(_build_ticket(), _build_ai_snapshot())
    ai_item = next(item for item in timeline["items"] if item["type"] == "ai_summary_generated")

    assert ai_item["metadata"] == {
        "summary_status": "fresh",
        "model_id": "timeline-model",
    }
    assert "prompt" not in ai_item["metadata"]


def test_missing_ticket_timeline_does_not_break_serialization() -> None:
    timeline = serialize_ticket_timeline(None)

    assert timeline["items"] == []
    assert timeline["warning"] == "Ticket history is temporarily unavailable."


async def test_ticket_workspace_includes_timeline_when_available() -> None:
    gateway = MiniAppGateway(
        backend_client_factory=build_backend_factory(TimelineBackendClient()),
        bot=MagicMock(),
    )

    workspace = await gateway.get_ticket_workspace(
        user=_build_user(),
        ticket_public_id=uuid4(),
    )

    assert "timeline" in workspace
    assert workspace["timeline"]["warning"] is None
    assert workspace["timeline"]["items"][0]["type"] == "ticket_created"


def _build_user() -> TelegramMiniAppUser:
    return TelegramMiniAppUser(
        telegram_user_id=1001,
        first_name="Anna",
        last_name=None,
        username="anna",
        language_code="ru",
    )


def _build_ticket() -> TicketDetailsSummary:
    public_id = uuid4()
    return TicketDetailsSummary(
        public_id=public_id,
        public_number="HD-100",
        client_chat_id=2002,
        status=TicketStatus.CLOSED,
        priority="normal",
        subject="Cannot sign in",
        assigned_operator_id=7,
        assigned_operator_name="Anna",
        assigned_operator_telegram_user_id=1001,
        created_at=datetime(2026, 4, 20, 10, 0, tzinfo=UTC),
        updated_at=datetime(2026, 4, 20, 10, 1, tzinfo=UTC),
        closed_at=datetime(2026, 4, 20, 10, 40, tzinfo=UTC),
        category_title="Access",
        tags=("vip",),
        message_history=(
            TicketMessageSummary(
                sender_type=TicketMessageSenderType.CLIENT,
                sender_operator_id=None,
                sender_operator_name=None,
                text="I cannot sign in.",
                created_at=datetime(2026, 4, 20, 10, 5, tzinfo=UTC),
            ),
            TicketMessageSummary(
                sender_type=TicketMessageSenderType.OPERATOR,
                sender_operator_id=7,
                sender_operator_name="Anna",
                text="We are checking your access.",
                created_at=datetime(2026, 4, 20, 10, 12, tzinfo=UTC),
            ),
        ),
        internal_notes=(
            TicketInternalNoteSummary(
                id=3,
                author_operator_id=7,
                author_operator_name="Anna",
                text="Checked profile sync.",
                created_at=datetime(2026, 4, 20, 10, 20, tzinfo=UTC),
            ),
        ),
    )


def _build_ai_snapshot() -> TicketAssistSnapshot:
    return TicketAssistSnapshot(
        available=True,
        summary_status=TicketSummaryStatus.FRESH,
        summary_generated_at=datetime(2026, 4, 20, 10, 30, tzinfo=UTC),
        status_note="Summary generated from ticket context.",
        model_id="timeline-model",
    )
