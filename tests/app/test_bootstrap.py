from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pytest import MonkeyPatch

from app import bootstrap
from app.bootstrap import RedisWorkflowRuntime
from infrastructure.config.settings import Settings


def build_settings(*, bot_token: str) -> Settings:
    return Settings.model_validate(
        {
            "app": {"dry_run": True},
            "bot": {"token": bot_token},
            "authorization": {"super_admin_telegram_user_ids": [42]},
            "postgres_expose_port": None,
            "redis_expose_port": None,
            "database": {
                "host": "postgres",
                "port": 5432,
                "user": "helpdesk",
                "password": "secret",
                "database": "helpdesk",
            },
            "redis": {
                "host": "redis",
                "port": 6379,
                "db": 0,
            },
            "logging": {"level": "INFO"},
        }
    )


def build_redis_workflow_runtime() -> RedisWorkflowRuntime:
    return RedisWorkflowRuntime(
        ticket_lock_manager=Mock(),
        global_rate_limiter=Mock(),
        chat_rate_limiter=Mock(),
        operator_presence=Mock(),
        ticket_live_session_store=Mock(),
        operator_active_ticket_store=Mock(),
        sla_deadline_scheduler=Mock(),
        ticket_stream_publisher=Mock(),
        ticket_stream_consumer=Mock(),
        sla_timeout_processor=Mock(),
    )


async def test_build_runtime_wires_same_redis_client_into_fsm_and_workflow(
    monkeypatch: MonkeyPatch,
) -> None:
    settings = build_settings(bot_token="123456:token")
    fake_engine = Mock()
    fake_session_factory = Mock()
    fake_redis = Mock()
    fake_storage = Mock()
    fake_storage.close = AsyncMock()
    fake_workflow = build_redis_workflow_runtime()
    fake_bot = Mock()
    fake_bot.session = SimpleNamespace(close=AsyncMock())
    fake_dispatcher = Mock()
    fake_dispatcher.workflow_data = {}
    fake_diagnostics_service = Mock()
    fake_backend_server = Mock()
    fake_backend_client_factory = Mock()

    build_engine_mock = Mock(return_value=fake_engine)
    build_session_factory_mock = Mock(return_value=fake_session_factory)
    build_redis_client_mock = Mock(return_value=fake_redis)
    build_fsm_storage_mock = Mock(return_value=fake_storage)
    build_redis_workflow_runtime_mock = Mock(return_value=fake_workflow)
    ping_redis_client_mock = AsyncMock(return_value=True)
    ping_database_engine_mock = AsyncMock(return_value=True)
    build_bot_mock = Mock(return_value=fake_bot)
    build_dispatcher_mock = Mock(return_value=fake_dispatcher)
    build_diagnostics_service_mock = Mock(return_value=fake_diagnostics_service)
    build_helpdesk_backend_server_mock = Mock(return_value=fake_backend_server)
    build_helpdesk_backend_client_factory_mock = Mock(return_value=fake_backend_client_factory)
    close_redis_client_mock = AsyncMock()
    dispose_engine_mock = AsyncMock()

    monkeypatch.setattr(bootstrap, "build_engine", build_engine_mock)
    monkeypatch.setattr(bootstrap, "build_session_factory", build_session_factory_mock)
    monkeypatch.setattr(bootstrap, "build_redis_client", build_redis_client_mock)
    monkeypatch.setattr(bootstrap, "build_fsm_storage", build_fsm_storage_mock)
    monkeypatch.setattr(
        bootstrap,
        "build_redis_workflow_runtime",
        build_redis_workflow_runtime_mock,
    )
    monkeypatch.setattr(bootstrap, "ping_database_engine", ping_database_engine_mock)
    monkeypatch.setattr(bootstrap, "ping_redis_client", ping_redis_client_mock)
    monkeypatch.setattr(bootstrap, "build_bot", build_bot_mock)
    monkeypatch.setattr(bootstrap, "build_dispatcher", build_dispatcher_mock)
    monkeypatch.setattr(
        bootstrap,
        "build_helpdesk_backend_server",
        build_helpdesk_backend_server_mock,
    )
    monkeypatch.setattr(
        bootstrap,
        "build_helpdesk_backend_client_factory",
        build_helpdesk_backend_client_factory_mock,
    )
    monkeypatch.setattr(bootstrap, "build_diagnostics_service", build_diagnostics_service_mock)
    monkeypatch.setattr(bootstrap, "close_redis_client", close_redis_client_mock)
    monkeypatch.setattr(bootstrap, "dispose_engine", dispose_engine_mock)

    runtime = await bootstrap.build_runtime(settings)

    assert runtime.redis is fake_redis
    assert runtime.fsm_storage is fake_storage
    assert runtime.redis_workflow is fake_workflow
    assert runtime.diagnostics_service is fake_diagnostics_service
    assert runtime.helpdesk_backend_client_factory is fake_backend_client_factory
    ping_database_engine_mock.assert_awaited_once_with(fake_engine)
    build_fsm_storage_mock.assert_called_once_with(fake_redis)
    build_redis_workflow_runtime_mock.assert_called_once_with(fake_redis)
    ping_redis_client_mock.assert_awaited_once_with(fake_redis)
    build_bot_mock.assert_called_once_with(settings.bot)
    build_dispatcher_mock.assert_called_once()
    build_helpdesk_backend_server_mock.assert_called_once()
    build_helpdesk_backend_client_factory_mock.assert_called_once_with(fake_backend_server)
    build_diagnostics_service_mock.assert_called_once()
    dispatcher_kwargs = build_dispatcher_mock.call_args.kwargs
    assert dispatcher_kwargs["storage"] is fake_storage
    assert dispatcher_kwargs["global_rate_limiter"] is fake_workflow.global_rate_limiter
    assert dispatcher_kwargs["chat_rate_limiter"] is fake_workflow.chat_rate_limiter
    assert dispatcher_kwargs["helpdesk_backend_client_factory"] is fake_backend_client_factory
    assert dispatcher_kwargs["operator_presence"] is fake_workflow.operator_presence
    assert dispatcher_kwargs["ticket_live_session_store"] is fake_workflow.ticket_live_session_store
    assert (
        dispatcher_kwargs["operator_active_ticket_store"]
        is fake_workflow.operator_active_ticket_store
    )
    assert fake_dispatcher.workflow_data["diagnostics_service"] is fake_diagnostics_service

    await bootstrap.close_runtime(runtime)

    fake_storage.close.assert_awaited_once()
    fake_bot.session.close.assert_awaited_once()
    close_redis_client_mock.assert_awaited_once_with(fake_redis)
    dispose_engine_mock.assert_awaited_once_with(fake_engine)


async def test_build_runtime_skips_dispatcher_wiring_without_bot_token(
    monkeypatch: MonkeyPatch,
) -> None:
    settings = build_settings(bot_token="")
    fake_engine = Mock()
    fake_session_factory = Mock()
    fake_redis = Mock()
    fake_storage = Mock()
    fake_storage.close = AsyncMock()
    fake_workflow = build_redis_workflow_runtime()
    fake_diagnostics_service = Mock()
    fake_backend_client_factory = Mock()

    build_bot = Mock()
    build_dispatcher = Mock()

    monkeypatch.setattr(bootstrap, "build_engine", Mock(return_value=fake_engine))
    monkeypatch.setattr(bootstrap, "build_session_factory", Mock(return_value=fake_session_factory))
    monkeypatch.setattr(bootstrap, "ping_database_engine", AsyncMock(return_value=True))
    monkeypatch.setattr(bootstrap, "build_redis_client", Mock(return_value=fake_redis))
    monkeypatch.setattr(bootstrap, "build_fsm_storage", Mock(return_value=fake_storage))
    monkeypatch.setattr(
        bootstrap,
        "build_redis_workflow_runtime",
        Mock(return_value=fake_workflow),
    )
    monkeypatch.setattr(bootstrap, "ping_redis_client", AsyncMock(return_value=True))
    monkeypatch.setattr(bootstrap, "build_bot", build_bot)
    monkeypatch.setattr(bootstrap, "build_dispatcher", build_dispatcher)
    monkeypatch.setattr(bootstrap, "build_helpdesk_backend_server", Mock(return_value=Mock()))
    monkeypatch.setattr(
        bootstrap,
        "build_helpdesk_backend_client_factory",
        Mock(return_value=fake_backend_client_factory),
    )
    monkeypatch.setattr(
        bootstrap,
        "build_diagnostics_service",
        Mock(return_value=fake_diagnostics_service),
    )
    monkeypatch.setattr(bootstrap, "close_redis_client", AsyncMock())
    monkeypatch.setattr(bootstrap, "dispose_engine", AsyncMock())

    runtime = await bootstrap.build_runtime(settings)

    assert runtime.bot is None
    assert runtime.dispatcher is None
    assert runtime.diagnostics_service is fake_diagnostics_service
    build_bot.assert_not_called()
    build_dispatcher.assert_not_called()


async def test_build_runtime_rejects_missing_bot_token_when_dry_run_is_disabled() -> None:
    settings = build_settings(bot_token="")
    settings.app.dry_run = False

    try:
        await bootstrap.build_runtime(settings)
    except RuntimeError as exc:
        assert str(exc) == "Невозможно запустить polling: BOT__TOKEN не задан."
    else:
        raise AssertionError("expected RuntimeError")


async def test_build_runtime_closes_resources_when_database_check_fails(
    monkeypatch: MonkeyPatch,
) -> None:
    settings = build_settings(bot_token="123456:token")
    fake_engine = Mock()
    dispose_engine_mock = AsyncMock()

    monkeypatch.setattr(bootstrap, "build_engine", Mock(return_value=fake_engine))
    monkeypatch.setattr(bootstrap, "build_session_factory", Mock(return_value=Mock()))
    monkeypatch.setattr(
        bootstrap,
        "ping_database_engine",
        AsyncMock(side_effect=RuntimeError("db down")),
    )
    monkeypatch.setattr(bootstrap, "dispose_engine", dispose_engine_mock)
    monkeypatch.setattr(bootstrap, "close_redis_client", AsyncMock())

    with pytest.raises(RuntimeError, match="db down"):
        await bootstrap.build_runtime(settings)

    dispose_engine_mock.assert_awaited_once_with(fake_engine)
