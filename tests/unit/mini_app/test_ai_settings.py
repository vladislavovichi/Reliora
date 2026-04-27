from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from http import HTTPStatus
from pathlib import Path
from types import MethodType
from typing import Any, cast
from urllib.parse import urlparse
from uuid import UUID, uuid4

import pytest

from application.ai.summaries import TicketAssistSnapshot, TicketReplyDraft, TicketSummaryStatus
from application.contracts.actors import RequestActor
from application.use_cases.ai.settings import InMemoryAISettingsRepository, RuntimeAISettings
from backend.grpc.contracts import HelpdeskBackendClient, HelpdeskBackendClientFactory
from domain.enums.roles import UserRole
from infrastructure.config.settings import MiniAppConfig
from mini_app.api import MiniAppGateway
from mini_app.auth import TelegramMiniAppUser
from mini_app.http import build_handler_class
from mini_app.launch import ResolvedMiniAppLaunch


def test_ai_settings_routes_are_super_admin_only(tmp_path: Path) -> None:
    gateway = StubAISettingsGateway()
    handler = _build_handler(gateway=gateway, static_dir=tmp_path)

    with pytest.raises(PermissionError):
        _dispatch_ai_settings(handler, role=UserRole.OPERATOR)
    assert gateway.get_called is False

    _dispatch_ai_settings(handler, role=UserRole.SUPER_ADMIN)

    assert handler.captured_status == HTTPStatus.OK
    assert gateway.get_called is True
    assert "api_token" not in handler.captured_payload


async def test_get_ai_settings_returns_current_safe_settings() -> None:
    repository = InMemoryAISettingsRepository(
        RuntimeAISettings(
            ai_reply_drafts_enabled=False,
            default_model_id="safe-model",
            max_history_messages=12,
            reply_draft_tone="formal",
        )
    )
    gateway = MiniAppGateway(
        backend_client_factory=_backend_factory(StubAIBackendClient()),
        ai_settings_repository=repository,
    )

    result = await gateway.get_ai_settings(user=_mini_app_user())

    assert result["settings"] == {
        "ai_summaries_enabled": True,
        "ai_macro_suggestions_enabled": True,
        "ai_reply_drafts_enabled": False,
        "ai_category_prediction_enabled": True,
        "default_model_id": "safe-model",
        "max_history_messages": 12,
        "reply_draft_tone": "formal",
        "operator_must_review_ai": True,
    }
    assert "api_token" not in result["settings"]


async def test_update_ai_settings_validates_and_saves_allowed_fields() -> None:
    repository = InMemoryAISettingsRepository()
    gateway = MiniAppGateway(
        backend_client_factory=_backend_factory(StubAIBackendClient()),
        ai_settings_repository=repository,
    )

    result = await gateway.update_ai_settings(
        user=_mini_app_user(),
        payload={
            "ai_summaries_enabled": False,
            "ai_macro_suggestions_enabled": False,
            "ai_reply_drafts_enabled": False,
            "ai_category_prediction_enabled": False,
            "default_model_id": " ops-model ",
            "max_history_messages": 500,
            "reply_draft_tone": "friendly",
            "operator_must_review_ai": False,
        },
    )

    settings = result["settings"]
    assert settings["ai_summaries_enabled"] is False
    assert settings["ai_macro_suggestions_enabled"] is False
    assert settings["ai_reply_drafts_enabled"] is False
    assert settings["ai_category_prediction_enabled"] is False
    assert settings["default_model_id"] == "ops-model"
    assert settings["max_history_messages"] == 100
    assert settings["reply_draft_tone"] == "friendly"
    assert settings["operator_must_review_ai"] is True


async def test_disabled_reply_drafts_return_unavailable_without_backend_call() -> None:
    client = StubAIBackendClient()
    gateway = MiniAppGateway(
        backend_client_factory=_backend_factory(client),
        ai_settings_repository=InMemoryAISettingsRepository(
            RuntimeAISettings(ai_reply_drafts_enabled=False, default_model_id="safe-model")
        ),
    )

    result = await gateway.generate_ticket_reply_draft(
        user=_mini_app_user(),
        ticket_public_id=uuid4(),
    )

    assert result["available"] is False
    assert result["unavailable_reason"] == "AI reply drafts are disabled by admin settings."
    assert result["model_id"] == "safe-model"
    assert client.reply_draft_calls == []


async def test_disabled_summaries_do_not_request_summary_generation() -> None:
    client = StubAIBackendClient()
    gateway = MiniAppGateway(
        backend_client_factory=_backend_factory(client),
        ai_settings_repository=InMemoryAISettingsRepository(
            RuntimeAISettings(ai_summaries_enabled=False)
        ),
    )

    result = await gateway.refresh_ticket_ai_summary(
        user=_mini_app_user(),
        ticket_public_id=uuid4(),
    )

    assert result["summary_status"] == "missing"
    assert result["short_summary"] is None
    assert client.snapshot_calls[0][1] is False


class StubAISettingsGateway:
    def __init__(self) -> None:
        self.get_called = False

    async def get_ai_settings(self, *, user: TelegramMiniAppUser) -> dict[str, Any]:
        del user
        self.get_called = True
        return {"settings": {"ai_reply_drafts_enabled": True}}

    async def update_ai_settings(
        self,
        *,
        user: TelegramMiniAppUser,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        del user, payload
        return {"settings": {"ai_reply_drafts_enabled": False}}


class StubAIBackendClient:
    def __init__(self) -> None:
        self.reply_draft_calls: list[tuple[UUID, RequestActor | None]] = []
        self.snapshot_calls: list[tuple[UUID, bool, RequestActor | None]] = []

    async def generate_ticket_reply_draft(
        self,
        *,
        ticket_public_id: UUID,
        actor: RequestActor | None = None,
    ) -> TicketReplyDraft | None:
        self.reply_draft_calls.append((ticket_public_id, actor))
        return TicketReplyDraft(available=True, reply_text="Hello", tone="polite")

    async def get_ticket_ai_assist_snapshot(
        self,
        *,
        ticket_public_id: UUID,
        refresh_summary: bool = False,
        actor: RequestActor | None = None,
    ) -> TicketAssistSnapshot | None:
        self.snapshot_calls.append((ticket_public_id, refresh_summary, actor))
        return TicketAssistSnapshot(
            available=True,
            summary_status=TicketSummaryStatus.FRESH,
            summary_generated_at=datetime(2026, 4, 20, 10, 0, tzinfo=UTC),
            short_summary="Stored summary",
            user_goal="Resolve issue",
            actions_taken="Checked account",
            current_status="Waiting",
            status_note=None,
            model_id="model",
        )


def _backend_factory(client: StubAIBackendClient) -> HelpdeskBackendClientFactory:
    @asynccontextmanager
    async def provide() -> AsyncIterator[HelpdeskBackendClient]:
        yield cast(HelpdeskBackendClient, client)

    return provide


def _build_handler(*, gateway: StubAISettingsGateway, static_dir: Path) -> Any:
    handler_cls = build_handler_class(
        gateway=gateway,  # type: ignore[arg-type]
        config=MiniAppConfig(listen_host="127.0.0.1", port=0, init_data_ttl_seconds=3600),
        bot_token="123:ABC",
        static_dir=static_dir,
    )
    handler = cast(Any, object.__new__(handler_cls))

    def write_json(self: Any, status: HTTPStatus, payload: dict[str, object]) -> None:
        self.captured_status = status
        self.captured_payload = payload

    def write_async_json(self: Any, awaitable: Any) -> None:
        self._write_json(HTTPStatus.OK, asyncio.run(awaitable))

    handler._write_json = MethodType(write_json, handler)
    handler._write_async_json = MethodType(write_async_json, handler)
    return handler


def _dispatch_ai_settings(handler: Any, *, role: UserRole) -> None:
    path = "/api/admin/ai-settings"
    handler._handle_authenticated_request(
        method="GET",
        path=path,
        parsed=urlparse(path),
        launch=ResolvedMiniAppLaunch(
            init_data="signed",
            source="test",
            client_source=None,
            diagnostics=(),
            is_telegram_webapp=True,
            has_telegram_user=True,
            attempted_sources=(),
            client_platform=None,
            client_version=None,
        ),
        user=_mini_app_user(),
        session={
            "access": {"telegram_user_id": 1001, "role": role.value},
            "user": {"telegram_user_id": 1001, "display_name": "Anna"},
        },
    )


def _mini_app_user() -> TelegramMiniAppUser:
    return TelegramMiniAppUser(
        telegram_user_id=1001,
        first_name="Anna",
        last_name=None,
        username="anna",
        language_code="ru",
    )
