from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from http import HTTPStatus
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import httpx

from application.contracts.actors import RequestActor
from application.use_cases.tickets.operator_invites import OperatorInviteCodeSummary
from backend.grpc.contracts import HelpdeskBackendClientFactory
from domain.enums.roles import UserRole
from infrastructure.config.settings import MiniAppConfig
from mini_app.api import MiniAppGateway
from mini_app.auth import TelegramMiniAppUser
from mini_app.context import MiniAppAuthenticatedContext, load_mini_app_session
from mini_app.http import create_mini_app
from mini_app.launch import ResolvedMiniAppLaunch
from mini_app.serializers import serialize_operator_invite
from tests.support.backend import FakeHelpdeskBackendClient, build_backend_client_factory


def test_serialize_operator_invite_includes_telegram_deep_link() -> None:
    invite = _invite()

    payload = serialize_operator_invite(invite, bot_username="@reliorabot")

    assert payload["code"] == "opr_test"
    assert payload["bot_username"] == "reliorabot"
    assert payload["telegram_deep_link"] == "https://t.me/reliorabot?start=opr_test"
    assert payload["link_available"] is True
    assert payload["link_unavailable_reason"] is None


def test_serialize_operator_invite_degrades_without_bot_username() -> None:
    invite = _invite()

    payload = serialize_operator_invite(invite)

    assert payload["code"] == "opr_test"
    assert payload["telegram_deep_link"] is None
    assert payload["bot_username"] is None
    assert payload["link_available"] is False
    assert payload["link_unavailable_reason"] == "bot_username_missing"


async def test_gateway_create_operator_invite_returns_deep_link_fields() -> None:
    client = StubInviteBackendClient()
    gateway = MiniAppGateway(
        backend_client_factory=_backend_factory(client),
        bot=MagicMock(),
        bot_username="reliorabot",
    )

    result = await gateway.create_operator_invite(user=_mini_app_user())

    assert client.calls == [RequestActor(telegram_user_id=1001)]
    assert result["invite"]["code"] == "opr_test"
    assert result["invite"]["telegram_deep_link"] == "https://t.me/reliorabot?start=opr_test"
    assert result["invite"]["link_available"] is True


def test_admin_invite_route_requires_super_admin(tmp_path: Path) -> None:
    gateway = StubInviteGateway()
    response = _request_invite(gateway=gateway, static_dir=tmp_path, role=UserRole.OPERATOR)

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert gateway.called is False


def test_admin_invite_route_returns_link_fields_for_super_admin(tmp_path: Path) -> None:
    gateway = StubInviteGateway()
    response = _request_invite(gateway=gateway, static_dir=tmp_path, role=UserRole.SUPER_ADMIN)

    assert response.status_code == HTTPStatus.OK
    assert gateway.called is True
    payload = response.json()
    assert payload["invite"]["code"] == "opr_test"
    assert payload["invite"]["telegram_deep_link"] == "https://t.me/reliorabot?start=opr_test"
    assert payload["invite"]["link_available"] is True


def test_static_renderer_invite_and_macro_copy_contracts() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("src/mini_app/static/assets").glob("renderers*.js")
    )
    source += "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("src/mini_app/static/assets/renderers").glob("*.js")
    )

    assert "Все макросы" not in source
    assert "Скопировать ссылку" in source
    assert "Скопировать код" in source
    assert "data-apply-macro" in source


class StubInviteBackendClient(FakeHelpdeskBackendClient):
    def __init__(self) -> None:
        self.calls: list[RequestActor | None] = []

    async def create_operator_invite(
        self,
        *,
        actor: RequestActor | None = None,
    ) -> OperatorInviteCodeSummary:
        self.calls.append(actor)
        return _invite()


class StubInviteGateway:
    def __init__(self) -> None:
        self.called = False

    async def create_operator_invite(self, *, user: TelegramMiniAppUser) -> dict[str, Any]:
        del user
        self.called = True
        return {
            "invite": serialize_operator_invite(_invite(), bot_username="reliorabot"),
        }


def _backend_factory(client: StubInviteBackendClient) -> HelpdeskBackendClientFactory:
    return build_backend_client_factory(client)


def _request_invite(*, gateway: StubInviteGateway, static_dir: Path, role: UserRole) -> Any:
    app = create_mini_app(
        gateway=gateway,  # type: ignore[arg-type]
        config=MiniAppConfig(listen_host="127.0.0.1", port=0, init_data_ttl_seconds=3600),
        bot_token="123:ABC",
        static_dir=static_dir,
    )

    async def load_session_override() -> MiniAppAuthenticatedContext:
        return MiniAppAuthenticatedContext(
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
            gateway=gateway,  # type: ignore[arg-type]
        )

    app.dependency_overrides[load_mini_app_session] = load_session_override
    return asyncio.run(_post_asgi(app, "/api/admin/invites"))


async def _post_asgi(app: Any, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://mini-app.test") as client:
        return await client.post(path)


def _mini_app_user() -> TelegramMiniAppUser:
    return TelegramMiniAppUser(
        telegram_user_id=1001,
        first_name="Anna",
        last_name=None,
        username="anna",
        language_code="ru",
    )


def _invite() -> OperatorInviteCodeSummary:
    return OperatorInviteCodeSummary(
        code="opr_test",
        expires_at=datetime(2026, 4, 15, 12, 0, tzinfo=UTC),
        max_uses=1,
    )
