from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, Mock

from aiogram.fsm.context import FSMContext

from application.contracts.actors import RequestActor
from application.services.stats import (
    AnalyticsCategorySnapshot,
    AnalyticsOperatorSnapshot,
    AnalyticsRatingBucket,
    AnalyticsWindow,
    HelpdeskAnalyticsSnapshot,
    OperatorTicketLoad,
    get_analytics_window_label,
)
from application.use_cases.analytics.exports import (
    AnalyticsExportFormat,
    AnalyticsSection,
    AnalyticsSnapshotExport,
    get_analytics_section_label,
)
from backend.grpc.contracts import HelpdeskBackendClientFactory
from bot.handlers.operator.stats import (
    handle_stats,
    handle_stats_export_file,
    handle_stats_export_menu,
    handle_stats_navigation,
)
from bot.texts.operator import (
    build_analytics_export_opened_text,
    build_analytics_export_ready_text,
    build_analytics_opened_text,
)
from tests.support.aiogram import (
    CallbackHarness,
    MessageHarness,
    build_callback_harness,
    build_message_harness,
)
from tests.support.backend import FakeHelpdeskBackendClient, build_backend_client_factory


class StatsBackendClient(FakeHelpdeskBackendClient):
    def __init__(
        self,
        *,
        snapshot: HelpdeskAnalyticsSnapshot | None = None,
        export: AnalyticsSnapshotExport | None = None,
    ) -> None:
        self._snapshot = snapshot
        self._export = export
        self.get_analytics_snapshot_mock = AsyncMock()
        self.export_analytics_snapshot_mock = AsyncMock()

    async def get_analytics_snapshot(
        self,
        *,
        window: AnalyticsWindow,
        actor: RequestActor | None = None,
    ) -> HelpdeskAnalyticsSnapshot:
        await self.get_analytics_snapshot_mock(window=window, actor=actor)
        assert self._snapshot is not None
        return self._snapshot

    async def export_analytics_snapshot(
        self,
        *,
        window: AnalyticsWindow,
        section: AnalyticsSection,
        format: AnalyticsExportFormat,
        actor: RequestActor | None = None,
    ) -> AnalyticsSnapshotExport:
        await self.export_analytics_snapshot_mock(
            window=window,
            section=section,
            format=format,
            actor=actor,
        )
        assert self._export is not None
        return self._export


class FakeFSMContext(FSMContext):
    def __init__(self) -> None:
        self.clear_mock = AsyncMock()

    async def clear(self) -> None:
        await self.clear_mock()


def _build_helpdesk_backend_client_factory(
    service: FakeHelpdeskBackendClient,
) -> HelpdeskBackendClientFactory:
    return build_backend_client_factory(service)


def _build_message() -> MessageHarness:
    return build_message_harness(
        user_id=1001,
        chat_id=3001,
        message_id=10,
        text="Статистика",
    )


def _build_callback() -> CallbackHarness:
    return build_callback_harness(
        user_id=1001,
        data="operator_stats:operators:7d",
        message=build_message_harness(
            user_id=1001,
            chat_id=3001,
            message_id=10,
            text="Статистика",
            with_edit_text=True,
        ),
    )


async def test_handle_stats_sends_overview_surface() -> None:
    message = _build_message()
    state = FakeFSMContext()
    snapshot = _build_snapshot()
    service = StatsBackendClient(snapshot=snapshot)
    global_rate_limiter = SimpleNamespace(allow=AsyncMock(return_value=True))
    operator_presence = SimpleNamespace(touch=AsyncMock())

    await handle_stats(
        message=message.message,
        state=state,
        helpdesk_backend_client_factory=_build_helpdesk_backend_client_factory(service),
        global_rate_limiter=global_rate_limiter,
        operator_presence=operator_presence,
    )

    message.answer.assert_awaited_once_with(ANY, reply_markup=ANY)
    service.get_analytics_snapshot_mock.assert_awaited_once_with(
        window=AnalyticsWindow.DAYS_7,
        actor=RequestActor(telegram_user_id=1001),
    )


async def test_handle_stats_navigation_updates_surface() -> None:
    callback = _build_callback()
    snapshot = _build_snapshot()
    service = StatsBackendClient(snapshot=snapshot)
    global_rate_limiter = SimpleNamespace(allow=AsyncMock(return_value=True))
    operator_presence = SimpleNamespace(touch=AsyncMock())

    await handle_stats_navigation(
        callback=callback.callback,
        callback_data=SimpleNamespace(section="operators", window="7d"),
        helpdesk_backend_client_factory=_build_helpdesk_backend_client_factory(service),
        global_rate_limiter=global_rate_limiter,
        operator_presence=operator_presence,
    )

    callback.answer.assert_awaited_once_with(
        build_analytics_opened_text(section="operators", window=AnalyticsWindow.DAYS_7)
    )
    assert callback.message.edit_text is not None
    callback.message.edit_text.assert_awaited_once_with(ANY, reply_markup=ANY)


async def test_handle_stats_export_menu_updates_surface() -> None:
    callback = _build_callback()
    snapshot = _build_snapshot()
    service = StatsBackendClient(snapshot=snapshot)
    global_rate_limiter = SimpleNamespace(allow=AsyncMock(return_value=True))
    operator_presence = SimpleNamespace(touch=AsyncMock())

    await handle_stats_export_menu(
        callback=callback.callback,
        callback_data=SimpleNamespace(action="open", section="operators", window="7d"),
        helpdesk_backend_client_factory=_build_helpdesk_backend_client_factory(service),
        global_rate_limiter=global_rate_limiter,
        operator_presence=operator_presence,
    )

    callback.answer.assert_awaited_once_with(
        build_analytics_export_opened_text(section="operators", window=AnalyticsWindow.DAYS_7)
    )
    assert callback.message.edit_text is not None
    callback.message.edit_text.assert_awaited_once_with(ANY, reply_markup=ANY)


async def test_handle_stats_export_file_delivers_document() -> None:
    callback = _build_callback()
    bot = Mock()
    bot.send_document = AsyncMock()
    export = AnalyticsSnapshotExport(
        format=AnalyticsExportFormat.CSV,
        filename="analytics-operators-7d.csv",
        content_type="text/csv",
        content=b"metric,value\nclosed,4\n",
        section=AnalyticsSection.OPERATORS,
        window=AnalyticsWindow.DAYS_7,
    )
    service = StatsBackendClient(export=export)
    global_rate_limiter = SimpleNamespace(allow=AsyncMock(return_value=True))
    operator_presence = SimpleNamespace(touch=AsyncMock())

    await handle_stats_export_file(
        callback=callback.callback,
        callback_data=SimpleNamespace(action="csv", section="operators", window="7d"),
        bot=bot,
        helpdesk_backend_client_factory=_build_helpdesk_backend_client_factory(service),
        global_rate_limiter=global_rate_limiter,
        operator_presence=operator_presence,
    )

    service.export_analytics_snapshot_mock.assert_awaited_once_with(
        window=AnalyticsWindow.DAYS_7,
        section=AnalyticsSection.OPERATORS,
        format=AnalyticsExportFormat.CSV,
        actor=RequestActor(telegram_user_id=1001),
    )
    callback.answer.assert_awaited_once_with(
        build_analytics_export_ready_text(section="operators", format_name="CSV")
    )
    _, kwargs = bot.send_document.await_args
    assert kwargs["caption"] == (
        f"Аналитика · {get_analytics_section_label(AnalyticsSection.OPERATORS)} · "
        f"{get_analytics_window_label(AnalyticsWindow.DAYS_7)}"
    )
    assert kwargs["document"].filename == "analytics-operators-7d.csv"


def _build_snapshot() -> HelpdeskAnalyticsSnapshot:
    operators = (
        AnalyticsOperatorSnapshot(
            operator_id=7,
            display_name="Operator One",
            active_ticket_count=3,
            closed_ticket_count=4,
            average_first_response_time_seconds=120,
            average_resolution_time_seconds=5400,
            average_satisfaction=4.8,
            feedback_count=3,
        ),
    )
    categories = (
        AnalyticsCategorySnapshot(
            category_id=1,
            category_title="Доступ и вход",
            created_ticket_count=5,
            open_ticket_count=2,
            closed_ticket_count=3,
            average_satisfaction=4.5,
            feedback_count=2,
            sla_breach_count=2,
        ),
    )
    return HelpdeskAnalyticsSnapshot(
        window=AnalyticsWindow.DAYS_7,
        total_open_tickets=6,
        queued_tickets_count=2,
        assigned_tickets_count=3,
        escalated_tickets_count=1,
        closed_tickets_count=4,
        tickets_per_operator=(
            OperatorTicketLoad(operator_id=7, display_name="Operator One", ticket_count=3),
        ),
        period_created_tickets_count=9,
        period_closed_tickets_count=5,
        average_first_response_time_seconds=126,
        average_resolution_time_seconds=7260,
        satisfaction_average=4.7,
        feedback_count=4,
        feedback_coverage_percent=80,
        rating_distribution=(AnalyticsRatingBucket(rating=5, count=3),),
        operator_snapshots=operators,
        category_snapshots=categories,
        best_operators_by_closures=operators,
        best_operators_by_satisfaction=operators,
        top_categories=categories,
        first_response_breach_count=2,
        resolution_breach_count=1,
        sla_categories=categories,
    )
