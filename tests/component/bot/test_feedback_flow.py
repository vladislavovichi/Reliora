from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

from application.contracts.actors import RequestActor
from application.use_cases.tickets.summaries import (
    TicketDetailsSummary,
    TicketFeedbackMutationResult,
    TicketFeedbackMutationStatus,
    TicketFeedbackSummary,
)
from backend.grpc.contracts import HelpdeskBackendClientFactory
from bot.handlers.user.feedback import (
    handle_ticket_feedback_comment,
    handle_ticket_feedback_comment_prompt,
    handle_ticket_feedback_rating,
    handle_ticket_feedback_skip,
)
from bot.handlers.user.states import UserFeedbackStates
from bot.keyboards.inline.feedback import build_ticket_feedback_comment_markup
from bot.texts.feedback import (
    TICKET_FEEDBACK_COMMENT_PROMPT_TEXT,
    TICKET_FEEDBACK_COMMENT_SAVED_TEXT,
    TICKET_FEEDBACK_SKIPPED_TEXT,
    TICKET_FEEDBACK_THANK_YOU_TEXT,
)
from domain.enums.tickets import TicketStatus
from tests.support.aiogram import (
    CallbackHarness,
    build_callback_harness,
    build_message_harness,
)
from tests.support.backend import FakeHelpdeskBackendClient, build_backend_client_factory


class FeedbackBackendClient(FakeHelpdeskBackendClient):
    def __init__(
        self,
        *,
        feedback_result: TicketFeedbackMutationResult | None = None,
        feedback: TicketFeedbackSummary | None = None,
        ticket_details: TicketDetailsSummary | None = None,
    ) -> None:
        self._feedback_result = feedback_result
        self._feedback = feedback
        self._ticket_details = ticket_details
        self.submit_ticket_feedback_rating_mock = AsyncMock()
        self.get_ticket_feedback_mock = AsyncMock()
        self.get_ticket_details_mock = AsyncMock()
        self.add_ticket_feedback_comment_mock = AsyncMock()

    async def submit_ticket_feedback_rating(
        self,
        *,
        ticket_public_id: UUID,
        client_chat_id: int,
        rating: int,
    ) -> TicketFeedbackMutationResult:
        await self.submit_ticket_feedback_rating_mock(
            ticket_public_id=ticket_public_id,
            client_chat_id=client_chat_id,
            rating=rating,
        )
        assert self._feedback_result is not None
        return self._feedback_result

    async def get_ticket_feedback(self, *, ticket_public_id: UUID) -> TicketFeedbackSummary | None:
        await self.get_ticket_feedback_mock(ticket_public_id=ticket_public_id)
        return self._feedback

    async def get_ticket_details(
        self,
        *,
        ticket_public_id: UUID,
        actor: RequestActor | None = None,
    ) -> TicketDetailsSummary | None:
        await self.get_ticket_details_mock(
            ticket_public_id=ticket_public_id,
            actor=actor,
        )
        return self._ticket_details

    async def add_ticket_feedback_comment(
        self,
        *,
        ticket_public_id: UUID,
        client_chat_id: int,
        comment: str,
    ) -> TicketFeedbackMutationResult:
        await self.add_ticket_feedback_comment_mock(
            ticket_public_id=ticket_public_id,
            client_chat_id=client_chat_id,
            comment=comment,
        )
        assert self._feedback_result is not None
        return self._feedback_result


def build_helpdesk_backend_client_factory(
    service: FakeHelpdeskBackendClient,
) -> HelpdeskBackendClientFactory:
    return build_backend_client_factory(service)


def build_feedback_callback(
    *,
    ticket_public_id: str,
    action: str,
    rating: int = 0,
) -> CallbackHarness:
    return build_callback_harness(
        user_id=2002,
        data=f"client_feedback:{action}:{ticket_public_id}:{rating}",
        with_edit_reply_markup=True,
        with_edit_text=True,
    )


def build_ticket_details(*, public_id: UUID) -> TicketDetailsSummary:
    return TicketDetailsSummary(
        public_id=public_id,
        public_number="HD-AAAA1111",
        client_chat_id=2002,
        status=TicketStatus.CLOSED,
        priority="normal",
        subject="Нужна помощь",
        assigned_operator_id=7,
        assigned_operator_name="Иван Петров",
        assigned_operator_telegram_user_id=1001,
        created_at=datetime(2026, 4, 8, 12, 0, tzinfo=UTC),
        tags=(),
        last_message_text="Добрый день",
        last_message_sender_type=None,
        message_history=(),
    )


def build_feedback_summary(
    *,
    public_id: UUID,
    rating: int,
    comment: str | None = None,
) -> TicketFeedbackSummary:
    return TicketFeedbackSummary(
        public_id=public_id,
        public_number="HD-AAAA1111",
        client_chat_id=2002,
        rating=rating,
        comment=comment,
        submitted_at=datetime(2026, 4, 8, 12, 30, tzinfo=UTC),
    )


async def test_handle_ticket_feedback_rating_saves_rating_and_offers_comment() -> None:
    ticket_public_id = uuid4()
    callback = build_feedback_callback(
        ticket_public_id=str(ticket_public_id),
        action="rate",
        rating=5,
    )
    feedback = build_feedback_summary(public_id=ticket_public_id, rating=5)
    service = FeedbackBackendClient(
        feedback_result=TicketFeedbackMutationResult(
            status=TicketFeedbackMutationStatus.CREATED,
            feedback=feedback,
        )
    )
    global_rate_limiter = SimpleNamespace(allow=AsyncMock(return_value=True))

    await handle_ticket_feedback_rating(
        callback=callback.callback,
        callback_data=SimpleNamespace(ticket_public_id=str(ticket_public_id), rating=5),
        helpdesk_backend_client_factory=build_helpdesk_backend_client_factory(service),
        global_rate_limiter=global_rate_limiter,
    )

    service.submit_ticket_feedback_rating_mock.assert_awaited_once_with(
        ticket_public_id=ticket_public_id,
        client_chat_id=2002,
        rating=5,
    )
    assert callback.message.edit_reply_markup is not None
    callback.message.edit_reply_markup.assert_awaited_once_with(reply_markup=None)
    callback.message.answer.assert_awaited_once_with(
        TICKET_FEEDBACK_THANK_YOU_TEXT,
        reply_markup=build_ticket_feedback_comment_markup(ticket_public_id=ticket_public_id),
    )
    callback.answer.assert_awaited_once_with()


async def test_handle_ticket_feedback_comment_prompt_sets_state_and_edits_message() -> None:
    ticket_public_id = uuid4()
    callback = build_feedback_callback(ticket_public_id=str(ticket_public_id), action="comment")
    feedback = build_feedback_summary(public_id=ticket_public_id, rating=5)
    ticket_details = build_ticket_details(public_id=ticket_public_id)
    service = FeedbackBackendClient(feedback=feedback, ticket_details=ticket_details)
    state = SimpleNamespace(set_state=AsyncMock(), set_data=AsyncMock())
    global_rate_limiter = SimpleNamespace(allow=AsyncMock(return_value=True))

    await handle_ticket_feedback_comment_prompt(
        callback=callback.callback,
        callback_data=SimpleNamespace(ticket_public_id=str(ticket_public_id)),
        state=state,
        helpdesk_backend_client_factory=build_helpdesk_backend_client_factory(service),
        global_rate_limiter=global_rate_limiter,
    )

    state.set_state.assert_awaited_once_with(UserFeedbackStates.writing_comment)
    state.set_data.assert_awaited_once_with({"ticket_public_id": str(ticket_public_id)})
    assert callback.message.edit_text is not None
    callback.message.edit_text.assert_awaited_once_with(
        TICKET_FEEDBACK_COMMENT_PROMPT_TEXT,
        reply_markup=None,
    )
    callback.answer.assert_awaited_once_with()


async def test_handle_ticket_feedback_skip_closes_prompt_cleanly() -> None:
    ticket_public_id = uuid4()
    callback = build_feedback_callback(ticket_public_id=str(ticket_public_id), action="skip")
    feedback = build_feedback_summary(public_id=ticket_public_id, rating=5)
    ticket_details = build_ticket_details(public_id=ticket_public_id)
    service = FeedbackBackendClient(feedback=feedback, ticket_details=ticket_details)
    global_rate_limiter = SimpleNamespace(allow=AsyncMock(return_value=True))

    await handle_ticket_feedback_skip(
        callback=callback.callback,
        callback_data=SimpleNamespace(ticket_public_id=str(ticket_public_id)),
        helpdesk_backend_client_factory=build_helpdesk_backend_client_factory(service),
        global_rate_limiter=global_rate_limiter,
    )

    assert callback.message.edit_text is not None
    callback.message.edit_text.assert_awaited_once_with(
        TICKET_FEEDBACK_SKIPPED_TEXT,
        reply_markup=None,
    )
    callback.answer.assert_awaited_once_with()


async def test_handle_ticket_feedback_comment_persists_comment_and_clears_state() -> None:
    ticket_public_id = uuid4()
    message = build_message_harness(
        user_id=2002,
        message_id=7,
        text="Спасибо за помощь",
    )

    service = FeedbackBackendClient(
        feedback_result=TicketFeedbackMutationResult(
            status=TicketFeedbackMutationStatus.UPDATED,
            feedback=build_feedback_summary(
                public_id=ticket_public_id,
                rating=5,
                comment="Спасибо за помощь",
            ),
        )
    )
    state = SimpleNamespace(
        get_data=AsyncMock(return_value={"ticket_public_id": str(ticket_public_id)}),
        clear=AsyncMock(),
    )
    global_rate_limiter = SimpleNamespace(allow=AsyncMock(return_value=True))
    chat_rate_limiter = SimpleNamespace(allow=AsyncMock(return_value=True))

    await handle_ticket_feedback_comment(
        message=message.message,
        state=state,
        helpdesk_backend_client_factory=build_helpdesk_backend_client_factory(service),
        global_rate_limiter=global_rate_limiter,
        chat_rate_limiter=chat_rate_limiter,
    )

    service.add_ticket_feedback_comment_mock.assert_awaited_once_with(
        ticket_public_id=ticket_public_id,
        client_chat_id=2002,
        comment="Спасибо за помощь",
    )
    state.clear.assert_awaited_once_with()
    message.answer.assert_awaited_once_with(TICKET_FEEDBACK_COMMENT_SAVED_TEXT)
