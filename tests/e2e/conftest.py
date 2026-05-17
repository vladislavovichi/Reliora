from __future__ import annotations

import os
import socket
from collections.abc import AsyncIterator
from typing import cast
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from application.contracts.ai import (
    AIServiceClientFactory,
    AnalyzedTicketSentimentResult,
)
from application.services.helpdesk.service import HelpdeskServiceFactory
from backend.grpc.client import build_helpdesk_backend_client_factory
from backend.grpc.contracts import HelpdeskBackendClient
from backend.grpc.server import build_helpdesk_backend_server
from infrastructure.config.settings import BackendAuthConfig, BackendServiceConfig, ResilienceConfig
from infrastructure.db.session import build_engine, build_session_factory
from infrastructure.runtime_factories import build_helpdesk_service_factory

_TEST_DB_HOST = os.environ.get("DATABASE__HOST", "127.0.0.1")
_TEST_DB_PORT = int(os.environ.get("DATABASE__PORT", "5432"))
_TEST_DB_USER = os.environ.get("DATABASE__USER", "helpdesk")
_TEST_DB_PASSWORD = os.environ.get("DATABASE__PASSWORD", "helpdesk")
_TEST_DB_NAME = os.environ.get("DATABASE__DATABASE", "helpdesk")
_TEST_DB_URL = (
    f"postgresql+asyncpg://{_TEST_DB_USER}:{_TEST_DB_PASSWORD}"
    f"@{_TEST_DB_HOST}:{_TEST_DB_PORT}/{_TEST_DB_NAME}"
)

_SUPER_ADMIN_ID = 42
_GRPC_AUTH_TOKEN = "e2e-test-internal-token"


def _free_tcp_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _build_mock_ai_factory() -> AIServiceClientFactory:
    client = AsyncMock()
    client.analyze_sentiment = AsyncMock(
        return_value=AnalyzedTicketSentimentResult(available=False)
    )
    client.predict_category = AsyncMock(return_value=None)
    client.summarize_ticket = AsyncMock(return_value=None)
    client.generate_reply_draft = AsyncMock(return_value=None)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return cast(AIServiceClientFactory, lambda: client)


@pytest.fixture(scope="session")
def db_engine() -> AsyncEngine:
    from infrastructure.config.settings import DatabaseConfig

    config = DatabaseConfig(
        host=_TEST_DB_HOST,
        port=_TEST_DB_PORT,
        user=_TEST_DB_USER,
        password=_TEST_DB_PASSWORD,
        database=_TEST_DB_NAME,
    )
    return build_engine(config)


@pytest.fixture(scope="session")
def db_session_factory(db_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return build_session_factory(db_engine)


@pytest.fixture(scope="session")
def helpdesk_service_factory(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> HelpdeskServiceFactory:
    return build_helpdesk_service_factory(
        db_session_factory,
        super_admin_telegram_user_ids=frozenset({_SUPER_ADMIN_ID}),
        ai_client_factory=_build_mock_ai_factory(),
    )


@pytest.fixture
async def grpc_backend(helpdesk_service_factory: HelpdeskServiceFactory):  # type: ignore[no-untyped-def]
    port = _free_tcp_port()
    server = build_helpdesk_backend_server(
        helpdesk_service_factory=helpdesk_service_factory,
        bind_target=f"127.0.0.1:{port}",
        auth_config=BackendAuthConfig(token=_GRPC_AUTH_TOKEN, caller="e2e-test"),
    )
    await server.start()
    try:
        yield port
    finally:
        await server.stop(grace=0)


@pytest.fixture
async def grpc_client(grpc_backend: int) -> AsyncIterator[HelpdeskBackendClient]:
    factory = build_helpdesk_backend_client_factory(
        BackendServiceConfig(host="127.0.0.1", port=grpc_backend),
        auth_config=BackendAuthConfig(token=_GRPC_AUTH_TOKEN, caller="e2e-test"),
        resilience_config=ResilienceConfig(),
    )
    async with factory() as client:
        yield client
