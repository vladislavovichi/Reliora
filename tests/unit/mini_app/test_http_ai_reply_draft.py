from __future__ import annotations

import asyncio
from http import HTTPStatus
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

from application.errors import NotFoundError, ValidationAppError
from domain.enums.roles import UserRole
from infrastructure.config.settings import MiniAppConfig
from mini_app.auth import TelegramMiniAppAuthError, TelegramMiniAppUser
from mini_app.context import MiniAppAuthenticatedContext, load_mini_app_session
from mini_app.http import create_mini_app
from mini_app.launch import ResolvedMiniAppLaunch


class StubGateway:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.called = False
        self.error = error

    async def generate_ticket_reply_draft(
        self,
        *,
        user: TelegramMiniAppUser,
        ticket_public_id: object,
    ) -> dict[str, object]:
        del user, ticket_public_id
        self.called = True
        if self.error is not None:
            raise self.error
        return {
            "available": True,
            "reply_text": "Здравствуйте! Проверим заявку.",
            "tone": "polite",
            "confidence": 0.8,
            "safety_note": None,
            "missing_information": None,
            "unavailable_reason": None,
            "model_id": "reply-model",
        }


def test_ai_reply_draft_route_rejects_plain_user(tmp_path: Path) -> None:
    gateway = StubGateway()
    response = _request_ai_reply_draft(gateway=gateway, static_dir=tmp_path, role=UserRole.USER)

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert gateway.called is False
    assert "операторам" in response.json()["error"]
    assert response.json()["code"] == "forbidden"


def test_ai_reply_draft_route_allows_operator(tmp_path: Path) -> None:
    gateway = StubGateway()
    response = _request_ai_reply_draft(gateway=gateway, static_dir=tmp_path, role=UserRole.OPERATOR)

    assert response.status_code == HTTPStatus.OK
    assert gateway.called is True
    assert response.json()["reply_text"] == "Здравствуйте! Проверим заявку."


def test_ai_reply_draft_route_normalizes_backend_unavailable_error(tmp_path: Path) -> None:
    gateway = StubGateway(error=ConnectionError("ai-service unavailable"))
    response = _request_ai_reply_draft(gateway=gateway, static_dir=tmp_path, role=UserRole.OPERATOR)

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.json()["code"] == "ai_unavailable"


def test_ai_reply_draft_route_normalizes_not_found_error(tmp_path: Path) -> None:
    gateway = StubGateway(error=NotFoundError("missing"))
    response = _request_ai_reply_draft(gateway=gateway, static_dir=tmp_path, role=UserRole.OPERATOR)

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()["code"] == "not_found"


def test_ai_reply_draft_route_normalizes_validation_error(tmp_path: Path) -> None:
    gateway = StubGateway(error=ValidationAppError("bad payload"))
    response = _request_ai_reply_draft(gateway=gateway, static_dir=tmp_path, role=UserRole.OPERATOR)

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json()["code"] == "validation_error"


def test_ai_reply_draft_route_normalizes_unauthorized_error(tmp_path: Path) -> None:
    gateway = StubGateway()
    app = create_mini_app(
        gateway=gateway,  # type: ignore[arg-type]
        config=MiniAppConfig(listen_host="127.0.0.1", port=0, init_data_ttl_seconds=3600),
        bot_token="123:ABC",
        static_dir=tmp_path,
    )

    async def raise_auth_error() -> object:
        raise TelegramMiniAppAuthError("missing", code="missing_init_data")

    app.dependency_overrides[load_mini_app_session] = raise_auth_error
    response = asyncio.run(_post_asgi(app, f"/api/tickets/{uuid4()}/ai-reply-draft"))

    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert response.json()["code"] == "unauthorized"


def _request_ai_reply_draft(*, gateway: StubGateway, static_dir: Path, role: UserRole) -> Any:
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
            user=TelegramMiniAppUser(
                telegram_user_id=1001,
                first_name="Anna",
                last_name=None,
                username="anna",
                language_code="ru",
            ),
            session={
                "access": {"telegram_user_id": 1001, "role": role.value},
                "user": {"telegram_user_id": 1001, "display_name": "Anna"},
            },
            gateway=gateway,  # type: ignore[arg-type]
        )

    app.dependency_overrides[load_mini_app_session] = load_session_override
    return asyncio.run(_post_asgi(app, f"/api/tickets/{uuid4()}/ai-reply-draft"))


async def _post_asgi(app: Any, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://mini-app.test") as client:
        return await client.post(path)
