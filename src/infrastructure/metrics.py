from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

import grpc
import grpc.aio
from prometheus_client import REGISTRY, Counter, Histogram, generate_latest

# --- Ticket lifecycle ---

TICKETS_CREATED = Counter(
    "helpdesk_tickets_created_total",
    "Total tickets created",
    ["source"],  # "bot" | "mini_app"
)

TICKETS_CLOSED = Counter(
    "helpdesk_tickets_closed_total",
    "Total tickets closed",
)

TICKETS_ESCALATED = Counter(
    "helpdesk_tickets_escalated_total",
    "Total tickets escalated",
    ["reason"],  # "manual" | "sla"
)

# --- Operator activity ---

OPERATOR_REPLIES = Counter(
    "helpdesk_operator_replies_total",
    "Total operator replies sent",
)

# --- AI operations ---

AI_REQUESTS = Counter(
    "helpdesk_ai_requests_total",
    "Total AI service requests",
    ["operation"],  # "category_predict" | "reply_draft" | "assist_snapshot"
)

AI_REQUEST_ERRORS = Counter(
    "helpdesk_ai_request_errors_total",
    "Total AI service request errors",
    ["operation"],
)

# --- HTTP (Mini App gateway) ---

HTTP_REQUEST_DURATION = Histogram(
    "helpdesk_http_request_duration_seconds",
    "Mini App HTTP request duration",
    ["method", "path_template", "status_code"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

HTTP_REQUESTS = Counter(
    "helpdesk_http_requests_total",
    "Total Mini App HTTP requests",
    ["method", "path_template", "status_code"],
)

# --- gRPC backend ---

GRPC_REQUEST_DURATION = Histogram(
    "helpdesk_grpc_request_duration_seconds",
    "Backend gRPC handler duration",
    ["method"],
    buckets=(0.005, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)

GRPC_REQUEST_ERRORS = Counter(
    "helpdesk_grpc_request_errors_total",
    "Total backend gRPC handler errors",
    ["method", "grpc_status"],
)

# --- SLA ---

SLA_CHECKS_RUN = Counter(
    "helpdesk_sla_checks_total",
    "Total SLA batch check runs",
)

SLA_ESCALATIONS = Counter(
    "helpdesk_sla_escalations_total",
    "Tickets auto-escalated by SLA",
)

SLA_REASSIGNMENTS = Counter(
    "helpdesk_sla_reassignments_total",
    "Tickets auto-reassigned by SLA",
)


def metrics_text() -> bytes:
    """Render current metrics in Prometheus text exposition format."""
    return generate_latest(REGISTRY)


class GrpcMetricsInterceptor(grpc.aio.ServerInterceptor):  # type: ignore[misc]
    """Records duration and error rate for every gRPC handler call."""

    async def intercept_service(  # type: ignore[override]
        self,
        continuation: Callable[..., Awaitable[Any]],
        handler_call_details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler:
        handler: grpc.RpcMethodHandler = await continuation(handler_call_details)
        if handler is None:
            return handler

        method = handler_call_details.method or "unknown"

        original = handler.unary_unary or handler.unary_stream

        if original is None:
            return handler

        async def timed_handler(request: Any, context: grpc.aio.ServicerContext) -> Any:  # type: ignore[return]
            start = time.perf_counter()
            try:
                result = await original(request, context)
                code = str(context.code() or grpc.StatusCode.OK)
                GRPC_REQUEST_DURATION.labels(method=method).observe(
                    time.perf_counter() - start
                )
                return result
            except Exception:
                GRPC_REQUEST_ERRORS.labels(
                    method=method, grpc_status=str(grpc.StatusCode.INTERNAL)
                ).inc()
                GRPC_REQUEST_DURATION.labels(method=method).observe(
                    time.perf_counter() - start
                )
                raise

        if handler.unary_unary is not None:
            return handler._replace(unary_unary=timed_handler)
        return handler._replace(unary_stream=timed_handler)
