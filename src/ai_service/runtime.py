from __future__ import annotations

from dataclasses import dataclass

from ai_service.grpc.server import AIServiceGrpcServer
from ai_service.service import AIApplicationService
from infrastructure.config.settings import Settings


@dataclass(slots=True)
class AIServiceRuntime:
    settings: Settings
    service: AIApplicationService
    grpc_server: AIServiceGrpcServer
