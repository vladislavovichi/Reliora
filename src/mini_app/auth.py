import json
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import parse_qsl

from aiogram.utils.web_app import WebAppInitData, safe_parse_webapp_init_data
from pydantic import ValidationError


class TelegramMiniAppAuthError(ValueError):
    """Raised when Telegram Mini App init data is missing or invalid."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(slots=True, frozen=True)
class TelegramMiniAppUser:
    telegram_user_id: int
    first_name: str
    last_name: str | None
    username: str | None
    language_code: str | None

    @property
    def display_name(self) -> str:
        parts = [self.first_name.strip()]
        if self.last_name:
            parts.append(self.last_name.strip())
        display_name = " ".join(part for part in parts if part)
        if display_name:
            return display_name
        if self.username:
            return self.username
        return f"Оператор {self.telegram_user_id}"


@dataclass(slots=True, frozen=True)
class ValidatedMiniAppInitData:
    raw_init_data: str
    auth_date: datetime
    user: TelegramMiniAppUser


def validate_telegram_mini_app_init_data(
    *,
    init_data: str,
    bot_token: str,
    max_age_seconds: int,
    now: datetime | None = None,
) -> ValidatedMiniAppInitData:
    normalized_init_data = init_data.strip()
    normalized_bot_token = bot_token.strip()
    _validate_required_inputs(
        init_data=normalized_init_data,
        bot_token=normalized_bot_token,
    )
    values = _parse_init_data_values(normalized_init_data)
    parsed = _safe_parse_init_data(
        init_data=normalized_init_data,
        bot_token=normalized_bot_token,
        values=values,
    )
    auth_date = _validate_auth_date(
        auth_date=parsed.auth_date,
        max_age_seconds=max_age_seconds,
        now=now,
    )
    user = _validate_user_payload(parsed)
    return ValidatedMiniAppInitData(
        raw_init_data=normalized_init_data,
        auth_date=auth_date,
        user=user,
    )


def _validate_required_inputs(*, init_data: str, bot_token: str) -> None:
    if not init_data:
        raise TelegramMiniAppAuthError(
            "Откройте рабочее место из Telegram. Данные запуска не получены.",
            code="missing_init_data",
        )
    if not bot_token:
        raise TelegramMiniAppAuthError(
            "Проверка рабочего места временно недоступна.",
            code="bot_token_missing",
        )


def _parse_init_data_values(init_data: str) -> dict[str, str]:
    try:
        pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise TelegramMiniAppAuthError(
            "Не удалось прочитать данные запуска. Откройте рабочее место заново.",
            code="malformed_init_data",
        ) from exc

    keys = [key for key, _value in pairs]
    duplicate_keys = {key for key in keys if keys.count(key) > 1}
    if duplicate_keys:
        raise TelegramMiniAppAuthError(
            "Telegram передал повреждённые данные запуска. Откройте рабочее место заново.",
            code="duplicate_init_data_keys",
        )

    values = dict(pairs)
    provided_hash = values.pop("hash", "").strip()
    if not provided_hash:
        raise TelegramMiniAppAuthError(
            "В данных запуска отсутствует подпись Telegram.",
            code="missing_signature",
        )
    return values


def _safe_parse_init_data(
    *,
    init_data: str,
    bot_token: str,
    values: dict[str, str],
) -> WebAppInitData:
    try:
        return safe_parse_webapp_init_data(bot_token, init_data)
    except json.JSONDecodeError as exc:
        raise TelegramMiniAppAuthError(
            "Профиль Telegram в данных запуска повреждён.",
            code="invalid_user_payload",
        ) from exc
    except ValidationError as exc:
        raise _validation_error_for_values(values) from exc
    except ValueError as exc:
        raise TelegramMiniAppAuthError(
            "Не удалось подтвердить запуск. Откройте рабочее место заново.",
            code="invalid_signature",
        ) from exc


def _validation_error_for_values(values: dict[str, str]) -> TelegramMiniAppAuthError:
    auth_timestamp_raw = values.get("auth_date", "").strip()
    if not auth_timestamp_raw:
        return TelegramMiniAppAuthError(
            "В данных запуска отсутствует время авторизации.",
            code="missing_auth_date",
        )
    try:
        int(auth_timestamp_raw)
    except ValueError:
        return TelegramMiniAppAuthError(
            "Telegram передал некорректное время авторизации.",
            code="invalid_auth_date",
        )
    if values.get("user", "").strip():
        return TelegramMiniAppAuthError(
            "Профиль Telegram в данных запуска неполный.",
            code="incomplete_user_payload",
        )
    return TelegramMiniAppAuthError(
        "Не удалось прочитать данные запуска. Откройте рабочее место заново.",
        code="malformed_init_data",
    )


def _validate_auth_date(
    *,
    auth_date: datetime,
    max_age_seconds: int,
    now: datetime | None,
) -> datetime:
    if auth_date.tzinfo is None:
        auth_date = auth_date.replace(tzinfo=UTC)

    current_time = now or datetime.now(UTC)
    if (auth_date - current_time).total_seconds() > 30:
        raise TelegramMiniAppAuthError(
            "Время запуска выглядит некорректно. Откройте рабочее место заново.",
            code="future_auth_date",
        )
    if max_age_seconds > 0 and (current_time - auth_date).total_seconds() > max_age_seconds:
        raise TelegramMiniAppAuthError(
            "Сеанс рабочего места устарел. Откройте рабочее место заново.",
            code="expired_init_data",
        )
    return auth_date


def _validate_user_payload(parsed: WebAppInitData) -> TelegramMiniAppUser:
    user = parsed.user
    if user is None:
        raise TelegramMiniAppAuthError(
            "В данных запуска отсутствует пользователь Telegram.",
            code="missing_user",
        )

    if user.id <= 0 or not user.first_name:
        raise TelegramMiniAppAuthError(
            "Профиль Telegram в данных запуска неполный.",
            code="incomplete_user_payload",
        )

    return TelegramMiniAppUser(
        telegram_user_id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        username=user.username,
        language_code=user.language_code,
    )
