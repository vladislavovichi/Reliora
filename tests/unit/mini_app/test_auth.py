import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import pytest

from mini_app.auth import TelegramMiniAppAuthError, validate_telegram_mini_app_init_data


def test_validate_telegram_mini_app_init_data_accepts_signed_payload() -> None:
    now = datetime(2026, 4, 14, 12, 0, tzinfo=UTC)
    init_data = _build_init_data(bot_token="123:ABC", auth_date=now)

    result = validate_telegram_mini_app_init_data(
        init_data=init_data,
        bot_token="123:ABC",
        max_age_seconds=3600,
        now=now,
    )

    assert result.user.telegram_user_id == 1001
    assert result.user.display_name == "Анна Смирнова"
    assert result.auth_date == now


def test_validate_telegram_mini_app_init_data_rejects_expired_payload() -> None:
    auth_date = datetime(2026, 4, 14, 9, 0, tzinfo=UTC)
    now = auth_date + timedelta(hours=2)
    init_data = _build_init_data(bot_token="123:ABC", auth_date=auth_date)

    with pytest.raises(TelegramMiniAppAuthError) as exc_info:
        validate_telegram_mini_app_init_data(
            init_data=init_data,
            bot_token="123:ABC",
            max_age_seconds=300,
            now=now,
        )

    assert exc_info.value.code == "expired_init_data"


def test_validate_telegram_mini_app_init_data_rejects_modified_payload() -> None:
    now = datetime(2026, 4, 14, 12, 0, tzinfo=UTC)
    init_data = _build_init_data(bot_token="123:ABC", auth_date=now).replace(
        "anna.support",
        "mallory",
    )

    with pytest.raises(TelegramMiniAppAuthError) as exc_info:
        validate_telegram_mini_app_init_data(
            init_data=init_data,
            bot_token="123:ABC",
            max_age_seconds=3600,
            now=now,
        )

    assert exc_info.value.code == "invalid_signature"


def test_validate_telegram_mini_app_init_data_rejects_missing_payload() -> None:
    with pytest.raises(TelegramMiniAppAuthError) as exc_info:
        validate_telegram_mini_app_init_data(
            init_data=" ",
            bot_token="123:ABC",
            max_age_seconds=3600,
        )

    assert exc_info.value.code == "missing_init_data"


def test_validate_telegram_mini_app_init_data_rejects_malformed_payload() -> None:
    with pytest.raises(TelegramMiniAppAuthError) as exc_info:
        validate_telegram_mini_app_init_data(
            init_data="user=%7Bbroken&hash",
            bot_token="123:ABC",
            max_age_seconds=3600,
        )

    assert exc_info.value.code == "malformed_init_data"


def test_validate_telegram_mini_app_init_data_rejects_malformed_user_json() -> None:
    now = datetime(2026, 4, 14, 12, 0, tzinfo=UTC)
    init_data = _build_init_data(
        bot_token="123:ABC",
        auth_date=now,
        user_payload='{"id":1001,}',
    )

    with pytest.raises(TelegramMiniAppAuthError) as exc_info:
        validate_telegram_mini_app_init_data(
            init_data=init_data,
            bot_token="123:ABC",
            max_age_seconds=3600,
            now=now,
        )

    assert exc_info.value.code == "invalid_user_payload"


def test_validate_telegram_mini_app_init_data_rejects_missing_user_payload() -> None:
    now = datetime(2026, 4, 14, 12, 0, tzinfo=UTC)
    init_data = _build_init_data(
        bot_token="123:ABC",
        auth_date=now,
        include_user=False,
    )

    with pytest.raises(TelegramMiniAppAuthError) as exc_info:
        validate_telegram_mini_app_init_data(
            init_data=init_data,
            bot_token="123:ABC",
            max_age_seconds=3600,
            now=now,
        )

    assert exc_info.value.code == "missing_user"


def test_validate_telegram_mini_app_init_data_rejects_missing_user_id() -> None:
    now = datetime(2026, 4, 14, 12, 0, tzinfo=UTC)
    init_data = _build_init_data(
        bot_token="123:ABC",
        auth_date=now,
        user_payload={"first_name": "Анна"},
    )

    with pytest.raises(TelegramMiniAppAuthError) as exc_info:
        validate_telegram_mini_app_init_data(
            init_data=init_data,
            bot_token="123:ABC",
            max_age_seconds=3600,
            now=now,
        )

    assert exc_info.value.code == "incomplete_user_payload"


def test_validate_telegram_mini_app_init_data_rejects_duplicate_keys() -> None:
    now = datetime(2026, 4, 14, 12, 0, tzinfo=UTC)
    init_data = _build_init_data(bot_token="123:ABC", auth_date=now)
    duplicated = f"{init_data}&auth_date={int(now.timestamp())}"

    with pytest.raises(TelegramMiniAppAuthError) as exc_info:
        validate_telegram_mini_app_init_data(
            init_data=duplicated,
            bot_token="123:ABC",
            max_age_seconds=3600,
            now=now,
        )

    assert exc_info.value.code == "duplicate_init_data_keys"


def _build_init_data(
    *,
    bot_token: str,
    auth_date: datetime,
    include_user: bool = True,
    user_payload: dict[str, object] | str | None = None,
) -> str:
    values = {
        "auth_date": str(int(auth_date.timestamp())),
        "query_id": "AAEAAAE",
    }
    if include_user:
        if user_payload is None:
            user_payload = {
                "id": 1001,
                "first_name": "Анна",
                "last_name": "Смирнова",
                "username": "anna.support",
                "language_code": "ru",
            }
        values["user"] = (
            user_payload
            if isinstance(user_payload, str)
            else json.dumps(
                user_payload,
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(values.items()))
    secret_key = hmac.new(
        b"WebAppData",
        bot_token.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    values["hash"] = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return urlencode(values)
