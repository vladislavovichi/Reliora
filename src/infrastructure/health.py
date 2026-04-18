from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import grpc
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

EXPECTED_HEALTH_FAILURES = (
    TimeoutError,
    OSError,
    RuntimeError,
    PermissionError,
    ValueError,
    SQLAlchemyError,
    RedisError,
    grpc.RpcError,
)


class ProbeStatus(StrEnum):
    OK = "OK"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass(slots=True, frozen=True)
class ProbeCheck:
    name: str
    category: str
    detail: str
    status: ProbeStatus
    affects_readiness: bool = True


@dataclass(slots=True, frozen=True)
class ProbeReport:
    checks: tuple[ProbeCheck, ...]

    @property
    def liveness_ok(self) -> bool:
        return all(
            check.status != ProbeStatus.FAIL
            for check in self.checks
            if check.category == "liveness"
        )

    @property
    def readiness_ok(self) -> bool:
        return all(
            check.status != ProbeStatus.FAIL
            for check in self.checks
            if check.category != "liveness" and check.affects_readiness
        )

    @property
    def has_warnings(self) -> bool:
        return any(check.status == ProbeStatus.WARN for check in self.checks)

    @property
    def summary(self) -> str:
        if not self.readiness_ok:
            return "FAIL"
        if self.has_warnings:
            return "DEGRADED"
        return "OK"

    @property
    def exit_code(self) -> int:
        return 0 if self.readiness_ok else 1

    def render(self) -> str:
        lines = [
            self.summary,
            f"[{'OK' if self.liveness_ok else 'FAIL'}] liveness",
            f"[{'OK' if self.readiness_ok else 'FAIL'}] readiness",
            *[
                f"[{check.status.value}] {check.category}/{check.name}: {check.detail}"
                for check in self.checks
            ],
        ]
        return "\n".join(lines)
