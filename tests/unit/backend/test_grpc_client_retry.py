from unittest.mock import AsyncMock, Mock

import grpc
import pytest

from application.errors import BackendUnavailableError, ValidationAppError
from backend.grpc.client import GrpcHelpdeskBackendClient
from infrastructure.config.settings import BackendAuthConfig


async def test_backend_grpc_client_retries_transient_unary_error() -> None:
    client = _backend_client()
    response = object()
    call = AsyncMock(side_effect=[_rpc_error(grpc.StatusCode.UNAVAILABLE, "down"), response])

    result = await client._invoke_unary(call, object(), retryable=True)

    assert result is response
    assert call.await_count == 2


async def test_backend_grpc_client_translates_final_transient_error() -> None:
    client = _backend_client()
    call = AsyncMock(
        side_effect=[
            _rpc_error(grpc.StatusCode.UNAVAILABLE, "backend down"),
            _rpc_error(grpc.StatusCode.UNAVAILABLE, "backend down"),
        ]
    )

    with pytest.raises(BackendUnavailableError, match="backend down"):
        await client._call_unary_raw(call, object(), retryable=True)

    assert call.await_count == 2


async def test_backend_grpc_client_does_not_retry_non_transient_error() -> None:
    client = _backend_client()
    call = AsyncMock(side_effect=_rpc_error(grpc.StatusCode.INVALID_ARGUMENT, "bad request"))

    with pytest.raises(ValidationAppError, match="bad request"):
        await client._call_unary_raw(call, object(), retryable=True)

    call.assert_awaited_once()


def _backend_client() -> GrpcHelpdeskBackendClient:
    return GrpcHelpdeskBackendClient(
        stub=Mock(),
        auth_config=BackendAuthConfig(token="test-token"),
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
