from __future__ import annotations

from urllib.parse import ParseResult, parse_qs
from uuid import UUID

from starlette.responses import Response

from application.errors import ValidationAppError
from application.use_cases.analytics.exports import AnalyticsExportFormat, AnalyticsSection
from application.use_cases.tickets.exports import TicketReportFormat
from mini_app.api import MiniAppGateway
from mini_app.auth import TelegramMiniAppUser
from mini_app.request_parsing import parse_analytics_window
from mini_app.responses import binary_response


async def export_analytics_response(
    *,
    gateway: MiniAppGateway,
    user: TelegramMiniAppUser,
    parsed: ParseResult,
) -> Response:
    window = parse_analytics_window(parsed)
    query = parse_qs(parsed.query)
    try:
        section = AnalyticsSection(query.get("section", ["overview"])[0])
        analytics_format = AnalyticsExportFormat(query.get("format", ["html"])[0])
    except ValueError as exc:
        raise ValidationAppError("Некорректные параметры экспорта аналитики.") from exc
    return binary_response(
        await gateway.export_analytics(
            user=user,
            window=window,
            section=section,
            format=analytics_format,
        )
    )


async def export_ticket_response(
    *,
    gateway: MiniAppGateway,
    user: TelegramMiniAppUser,
    ticket_public_id: UUID,
    parsed: ParseResult,
) -> Response:
    query = parse_qs(parsed.query)
    try:
        ticket_format = TicketReportFormat(query.get("format", ["html"])[0])
    except ValueError as exc:
        raise ValidationAppError("Некорректный формат экспорта заявки.") from exc
    return binary_response(
        await gateway.export_ticket(
            user=user,
            ticket_public_id=ticket_public_id,
            format=ticket_format,
        )
    )
