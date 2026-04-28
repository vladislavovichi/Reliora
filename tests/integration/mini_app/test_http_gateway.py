from __future__ import annotations

import hashlib
import hmac
import io
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlencode
from uuid import uuid4

from domain.enums.roles import UserRole
from infrastructure.config.settings import MiniAppConfig
from mini_app.auth import TelegramMiniAppUser
from mini_app.http import build_handler_class

BOT_TOKEN = "123:ABC"


class StubGateway:
    def __init__(
        self,
        *,
        role: UserRole = UserRole.OPERATOR,
        dashboard_error: Exception | None = None,
        ticket_error: Exception | None = None,
    ) -> None:
        self.role = role
        self.dashboard_error = dashboard_error
        self.ticket_error = ticket_error

    async def get_session(self, *, user: TelegramMiniAppUser) -> dict[str, object]:
        return {
            "access": {
                "telegram_user_id": user.telegram_user_id,
                "role": self.role.value,
            },
            "user": {"display_name": user.display_name},
        }

    async def get_dashboard(self, *, user: TelegramMiniAppUser) -> dict[str, object]:
        del user
        if self.dashboard_error is not None:
            raise self.dashboard_error
        return {"ok": True}

    async def get_ticket_workspace(
        self,
        *,
        user: TelegramMiniAppUser,
        ticket_public_id: object,
    ) -> dict[str, object]:
        del user, ticket_public_id
        if self.ticket_error is not None:
            raise self.ticket_error
        return {"ticket": {"public_id": "ticket"}}


def test_http_session_accepts_valid_telegram_init_data() -> None:
    status, payload = request_json(
        gateway=StubGateway(),
        path="/api/session",
        init_data=build_init_data(auth_date=datetime.now(UTC)),
    )

    assert status == 200
    assert payload["access"]["role"] == "operator"
    assert payload["user"]["display_name"] == "Анна Смирнова"


def test_http_rejects_invalid_telegram_init_data() -> None:
    status, payload = request_json(
        gateway=StubGateway(),
        path="/api/session",
        init_data="auth_date=1&hash=bad",
    )

    assert status == 401
    assert payload["code"] in {"malformed_init_data", "invalid_signature"}


def test_http_rejects_expired_telegram_init_data() -> None:
    status, payload = request_json(
        gateway=StubGateway(),
        path="/api/session",
        init_data=build_init_data(auth_date=datetime.now(UTC) - timedelta(minutes=2)),
        init_data_ttl_seconds=1,
    )

    assert status == 401
    assert payload["code"] == "expired_init_data"


def test_http_forbids_user_role_from_operator_dashboard() -> None:
    status, payload = request_json(
        gateway=StubGateway(role=UserRole.USER),
        path="/api/dashboard",
        init_data=build_init_data(auth_date=datetime.now(UTC)),
    )

    assert status == 403
    assert payload["code"] == "access_denied"


def test_http_maps_missing_ticket_to_not_found() -> None:
    status, payload = request_json(
        gateway=StubGateway(ticket_error=LookupError("Заявка не найдена.")),
        path=f"/api/tickets/{uuid4()}",
        init_data=build_init_data(auth_date=datetime.now(UTC)),
    )

    assert status == 404
    assert payload == {"error": "Заявка не найдена.", "code": "not_found"}


def test_http_maps_backend_unavailable_to_safe_response() -> None:
    status, payload = request_json(
        gateway=StubGateway(dashboard_error=ConnectionError("backend token rejected")),
        path="/api/dashboard",
        init_data=build_init_data(auth_date=datetime.now(UTC)),
    )

    assert status == 503
    assert payload["code"] == "backend_unavailable"
    assert "token" not in payload["error"].lower()


def request_json(
    *,
    gateway: StubGateway,
    path: str,
    init_data: str,
    init_data_ttl_seconds: int = 3600,
) -> tuple[int, dict[str, Any]]:
    handler_cls = build_handler_class(
        gateway=cast(Any, gateway),
        config=MiniAppConfig(
            listen_host="127.0.0.1",
            port=0,
            init_data_ttl_seconds=init_data_ttl_seconds,
        ),
        bot_token=BOT_TOKEN,
        static_dir=Path("src/mini_app/static"),
    )
    request = (
        f"GET {path} HTTP/1.1\r\nHost: mini-app.test\r\nX-Telegram-Init-Data: {init_data}\r\n\r\n"
    ).encode()
    connection = FakeSocket(request)
    handler_cls(cast(Any, connection), ("127.0.0.1", 12345), cast(Any, object()))
    status, _headers, body = parse_http_response(connection.output.getvalue())
    return status, cast(dict[str, Any], json.loads(body.decode()))


class FakeSocket:
    def __init__(self, request: bytes) -> None:
        self.input = io.BytesIO(request)
        self.output = io.BytesIO()

    def makefile(self, mode: str, buffering: int | None = None) -> io.BytesIO:
        del buffering
        if "r" in mode:
            return self.input
        return self.output

    def sendall(self, data: bytes) -> None:
        self.output.write(data)


def parse_http_response(raw: bytes) -> tuple[int, dict[str, str], bytes]:
    header_bytes, body = raw.split(b"\r\n\r\n", 1)
    header_lines = header_bytes.decode("iso-8859-1").split("\r\n")
    status = int(header_lines[0].split()[1])
    headers = dict(line.split(": ", 1) for line in header_lines[1:] if ": " in line)
    return status, headers, body


def build_init_data(*, auth_date: datetime) -> str:
    values = {
        "auth_date": str(int(auth_date.timestamp())),
        "query_id": "AAEAAAE",
        "user": json.dumps(
            {
                "id": 1001,
                "first_name": "Анна",
                "last_name": "Смирнова",
                "username": "anna.support",
                "language_code": "ru",
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }
    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(values.items()))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode("utf-8"), hashlib.sha256).digest()
    values["hash"] = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return urlencode(values)
