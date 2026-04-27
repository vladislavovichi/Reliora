from __future__ import annotations

import asyncio
from http import HTTPStatus
from pathlib import Path
from types import MethodType
from typing import Any, cast
from urllib.parse import urlparse
from uuid import uuid4

from domain.enums.roles import UserRole
from infrastructure.config.settings import MiniAppConfig
from mini_app.auth import TelegramMiniAppAuthError, TelegramMiniAppUser
from mini_app.http import build_handler_class
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
    handler = _build_handler(gateway=gateway, static_dir=tmp_path)

    _dispatch_authenticated(handler, role=UserRole.USER)

    assert handler.captured_status == HTTPStatus.FORBIDDEN
    assert gateway.called is False
    assert "операторам" in handler.captured_payload["error"]
    assert handler.captured_payload["code"] == "forbidden"


def test_ai_reply_draft_route_allows_operator(tmp_path: Path) -> None:
    gateway = StubGateway()
    handler = _build_handler(gateway=gateway, static_dir=tmp_path)

    _dispatch_authenticated(handler, role=UserRole.OPERATOR)

    assert handler.captured_status == HTTPStatus.OK
    assert gateway.called is True
    assert handler.captured_payload["reply_text"] == "Здравствуйте! Проверим заявку."


def test_ai_reply_draft_route_normalizes_backend_unavailable_error(tmp_path: Path) -> None:
    gateway = StubGateway(error=ConnectionError("ai-service unavailable"))
    handler = _build_handler(gateway=gateway, static_dir=tmp_path)

    _dispatch_via_request(handler, role=UserRole.OPERATOR)

    assert handler.captured_status == HTTPStatus.SERVICE_UNAVAILABLE
    assert handler.captured_payload["code"] == "ai_unavailable"


def test_ai_reply_draft_route_normalizes_not_found_error(tmp_path: Path) -> None:
    gateway = StubGateway(error=LookupError("missing"))
    handler = _build_handler(gateway=gateway, static_dir=tmp_path)

    _dispatch_via_request(handler, role=UserRole.OPERATOR)

    assert handler.captured_status == HTTPStatus.NOT_FOUND
    assert handler.captured_payload["code"] == "not_found"


def test_ai_reply_draft_route_normalizes_validation_error(tmp_path: Path) -> None:
    gateway = StubGateway(error=ValueError("bad payload"))
    handler = _build_handler(gateway=gateway, static_dir=tmp_path)

    _dispatch_via_request(handler, role=UserRole.OPERATOR)

    assert handler.captured_status == HTTPStatus.BAD_REQUEST
    assert handler.captured_payload["code"] == "validation_error"


def test_ai_reply_draft_route_normalizes_unauthorized_error(tmp_path: Path) -> None:
    gateway = StubGateway()
    handler = _build_handler(gateway=gateway, static_dir=tmp_path)

    def load_session(self: Any) -> object:
        raise TelegramMiniAppAuthError("missing", code="missing_init_data")

    handler._load_session = MethodType(load_session, handler)
    handler.path = f"/api/tickets/{uuid4()}/ai-reply-draft"
    handler._dispatch("POST")

    assert handler.captured_status == HTTPStatus.UNAUTHORIZED
    assert handler.captured_payload["code"] == "unauthorized"


def _build_handler(*, gateway: StubGateway, static_dir: Path) -> Any:
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


def _dispatch_authenticated(handler: Any, *, role: UserRole) -> None:
    path = f"/api/tickets/{uuid4()}/ai-reply-draft"
    handler._handle_authenticated_request(
        method="POST",
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
    )


def _dispatch_via_request(handler: Any, *, role: UserRole) -> None:
    def load_session(self: Any) -> object:
        return (
            ResolvedMiniAppLaunch(
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
            TelegramMiniAppUser(
                telegram_user_id=1001,
                first_name="Anna",
                last_name=None,
                username="anna",
                language_code="ru",
            ),
            {
                "access": {"telegram_user_id": 1001, "role": role.value},
                "user": {"telegram_user_id": 1001, "display_name": "Anna"},
            },
        )

    handler._load_session = MethodType(load_session, handler)
    handler.path = f"/api/tickets/{uuid4()}/ai-reply-draft"
    handler._dispatch("POST")
