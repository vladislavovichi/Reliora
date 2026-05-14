from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import ParseResult, parse_qs
from uuid import UUID

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator
from starlette.requests import Request

from application.errors import ValidationAppError
from application.services.stats import AnalyticsWindow

UUID_ROUTE_PATTERN = re.compile(r"^[0-9a-fA-F-]{36}$")


class MiniAppRouteNotFound(LookupError):
    pass


class AssignTicketPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    telegram_user_id: int
    display_name: str
    username: str | None = None

    @field_validator("telegram_user_id", mode="before")
    @classmethod
    def validate_telegram_user_id(cls, value: object) -> int:
        if not isinstance(value, int):
            raise ValueError("Поле telegram_user_id должно быть числом.")
        return value

    @field_validator("display_name", mode="before")
    @classmethod
    def validate_display_name(cls, value: object) -> str:
        return normalize_required_string(value, key="display_name")

    @field_validator("username", mode="before")
    @classmethod
    def validate_username(cls, value: object) -> str | None:
        return normalize_optional_string(value, key="username")


class TicketNotePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    text: str

    @field_validator("text", mode="before")
    @classmethod
    def validate_text(cls, value: object) -> str:
        return normalize_required_string(value, key="text")


def parse_analytics_window(parsed: ParseResult) -> AnalyticsWindow:
    query = parse_qs(parsed.query)
    try:
        return AnalyticsWindow(query.get("window", ["7d"])[0])
    except ValueError as exc:
        raise ValidationAppError("Некорректное окно аналитики.") from exc


async def read_json_body(request: Request) -> dict[str, Any]:
    payload = await request.body()
    if not payload:
        payload = b"{}"
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationAppError("Не удалось разобрать JSON payload.") from exc
    if not isinstance(decoded, dict):
        raise ValidationAppError("JSON payload должен быть объектом.")
    return decoded


async def read_json_model[ModelT: BaseModel](
    request: Request,
    model_type: type[ModelT],
) -> ModelT:
    payload = await read_json_body(request)
    try:
        return model_type.model_validate(payload)
    except ValidationError as exc:
        raise ValidationAppError(_validation_error_message(exc)) from exc


def parse_ticket_public_id(raw_value: str) -> UUID | None:
    if UUID_ROUTE_PATTERN.fullmatch(raw_value) is None:
        return None
    try:
        return UUID(raw_value)
    except ValueError:
        return None


def parse_positive_int_path(raw_value: str) -> int | None:
    if not raw_value.isdigit():
        return None
    return int(raw_value)


def normalize_required_string(value: object, *, key: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"Поле {key} должно быть строкой.")
    normalized = " ".join(value.split())
    if not normalized:
        raise ValueError(f"Поле {key} не должно быть пустым.")
    return normalized


def normalize_optional_string(value: object, *, key: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"Поле {key} должно быть строкой.")
    normalized = value.strip()
    return normalized or None


def _validation_error_message(exc: ValidationError) -> str:
    for error in exc.errors():
        message = error.get("msg")
        if isinstance(message, str):
            return message.removeprefix("Value error, ")
    return "Некорректный запрос."
