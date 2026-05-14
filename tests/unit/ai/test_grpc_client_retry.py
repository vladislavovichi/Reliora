from unittest.mock import AsyncMock, Mock

import grpc
import pytest

from ai_service.grpc.client import GrpcAIServiceClient
from application.errors import AIUnavailableError, ValidationAppError
from infrastructure.config.settings import AIServiceAuthConfig


async def test_ai_grpc_client_retries_transient_unary_error() -> None:
    client = _ai_client()
    response = object()
    call = AsyncMock(side_effect=[_rpc_error(grpc.StatusCode.UNAVAILABLE, "down"), response])

    result = await client._invoke_unary(call, object(), retryable=True)

    assert result is response
    assert call.await_count == 2


async def test_ai_grpc_client_translates_final_transient_error() -> None:
    client = _ai_client()
    call = AsyncMock(
        side_effect=[
            _rpc_error(grpc.StatusCode.DEADLINE_EXCEEDED, "ai timed out"),
            _rpc_error(grpc.StatusCode.DEADLINE_EXCEEDED, "ai timed out"),
        ]
    )

    with pytest.raises(AIUnavailableError, match="ai timed out"):
        await client._invoke_unary(call, object(), retryable=True)

    assert call.await_count == 2


async def test_ai_grpc_client_does_not_retry_non_transient_error() -> None:
    client = _ai_client()
    call = AsyncMock(side_effect=_rpc_error(grpc.StatusCode.INVALID_ARGUMENT, "bad request"))

    with pytest.raises(ValidationAppError, match="bad request"):
        await client._invoke_unary(call, object(), retryable=True)

    call.assert_awaited_once()


def _ai_client() -> GrpcAIServiceClient:
    return GrpcAIServiceClient(
        stub=Mock(),
        auth_config=AIServiceAuthConfig(token="test-token"),
        request_timeout_seconds=1.0,
        read_retry_attempts=2,
        retry_backoff_seconds=0.0,
    )


def _rpc_error(code: grpc.StatusCode, details: str) -> grpc.aio.AioRpcError:
    return grpc.aio.AioRpcError(
        code,
        grpc.aio.Metadata(),
        grpc.aio.Metadata(),
        details,
    )
