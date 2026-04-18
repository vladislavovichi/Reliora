from __future__ import annotations

from mini_app.launch import resolve_mini_app_launch


def test_resolve_mini_app_launch_prefers_header_value() -> None:
    launch = resolve_mini_app_launch(
        path="/api/session?init_data=query-value",
        headers={
            "X-Telegram-Init-Data": "header-value",
            "X-Mini-App-Launch-Source": "telegram-web-app",
            "X-Mini-App-Telegram-WebApp": "present",
            "X-Mini-App-Telegram-User": "present",
            "X-Mini-App-Attempted-Sources": "telegram-web-app,query:tgWebAppData",
            "X-Mini-App-Client-Diagnostics": "telegram-web-app:present,telegram-user:present",
            "X-Mini-App-Telegram-Platform": "android",
            "X-Mini-App-Telegram-Version": "9.1",
        },
    )

    assert launch.init_data == "header-value"
    assert launch.source == "header:x-telegram-init-data"
    assert launch.client_source == "telegram-web-app"
    assert launch.is_telegram_webapp is True
    assert launch.has_telegram_user is True
    assert launch.attempted_sources == ("telegram-web-app", "query:tgWebAppData")
    assert launch.client_platform == "android"
    assert launch.client_version == "9.1"
    assert "client:telegram-web-app:present" in launch.diagnostics


def test_resolve_mini_app_launch_supports_telegram_query_fallback() -> None:
    launch = resolve_mini_app_launch(
        path="/api/session?tgWebAppData=user%3D1%26hash%3Dabc",
        headers={},
    )

    assert launch.init_data == "user=1&hash=abc"
    assert launch.source == "query:tgWebAppData"


def test_resolve_mini_app_launch_marks_missing_init_data_with_diagnostics() -> None:
    launch = resolve_mini_app_launch(
        path="/api/session?tgWebAppVersion=8.0",
        headers={},
    )

    assert launch.init_data == ""
    assert launch.source == "missing"
    assert "telegram-launch-markers-present" in launch.diagnostics
    assert "init_data_missing" in launch.diagnostics


def test_resolve_mini_app_launch_reads_authorization_header() -> None:
    launch = resolve_mini_app_launch(
        path="/api/session",
        headers={"Authorization": "TMA signed-init-data"},
    )

    assert launch.init_data == "signed-init-data"
    assert launch.source == "header:authorization-tma"
