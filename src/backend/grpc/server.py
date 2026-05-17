from __future__ import annotations

from dataclasses import dataclass, field

import grpc

from application.services.helpdesk.service import HelpdeskServiceFactory
from backend.grpc.generated import helpdesk_pb2_grpc
from backend.grpc.server_analytics import HelpdeskBackendAnalyticsGrpcMixin
from backend.grpc.server_base import HelpdeskBackendGrpcServiceBase
from backend.grpc.server_operations import HelpdeskBackendOperationsGrpcMixin
from backend.grpc.server_ticketing import HelpdeskBackendTicketingGrpcMixin
from infrastructure.config.settings import BackendAuthConfig
from infrastructure.metrics import GrpcMetricsInterceptor


@dataclass(slots=True)
class HelpdeskBackendGrpcService(
    HelpdeskBackendTicketingGrpcMixin,
    HelpdeskBackendOperationsGrpcMixin,
    HelpdeskBackendAnalyticsGrpcMixin,
    HelpdeskBackendGrpcServiceBase,
    helpdesk_pb2_grpc.HelpdeskBackendServiceServicer,
):
    helpdesk_service_factory: HelpdeskServiceFactory
    auth_config: BackendAuthConfig


@dataclass(slots=True)
class HelpdeskBackendGrpcServer:
    helpdesk_service_factory: HelpdeskServiceFactory
    bind_target: str
    auth_config: BackendAuthConfig
    server: grpc.aio.Server = field(init=False)
    bound_port: int = field(init=False)

    def __post_init__(self) -> None:
        self.server = grpc.aio.server(interceptors=[GrpcMetricsInterceptor()])
        helpdesk_pb2_grpc.add_HelpdeskBackendServiceServicer_to_server(
            HelpdeskBackendGrpcService(
                helpdesk_service_factory=self.helpdesk_service_factory,
                auth_config=self.auth_config,
            ),
            self.server,
        )
        self.bound_port = self.server.add_insecure_port(self.bind_target)
        if self.bound_port == 0:
            raise RuntimeError(f"Не удалось открыть gRPC порт {self.bind_target}.")

    async def start(self) -> None:
        await self.server.start()

    async def stop(self, grace: float = 5.0) -> None:
        await self.server.stop(grace)

    async def wait_for_termination(self) -> None:
        await self.server.wait_for_termination()


def build_helpdesk_backend_server(
    *,
    helpdesk_service_factory: HelpdeskServiceFactory,
    bind_target: str,
    auth_config: BackendAuthConfig,
) -> HelpdeskBackendGrpcServer:
    return HelpdeskBackendGrpcServer(
        helpdesk_service_factory=helpdesk_service_factory,
        bind_target=bind_target,
        auth_config=auth_config,
    )
