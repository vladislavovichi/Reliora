from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.contracts.repositories import OperatorTicketLoadRecord
from domain.enums.tickets import TicketEventType, TicketStatus
from infrastructure.db.models.catalog import TicketCategory
from infrastructure.db.models.feedback import TicketFeedback
from infrastructure.db.models.operator import Operator
from infrastructure.db.models.ticket import Ticket as TicketModel
from infrastructure.db.models.ticket import TicketEvent
from infrastructure.db.repositories.base import (
    CategoryFeedbackStatsRow,
    CategoryTicketCountRow,
    OperatorClosureStatsRow,
    OperatorTicketLoadRow,
    RatingDistributionRow,
    SLABreachCountRow,
)


class SqlAlchemyTicketMetricsRepository:
    session: AsyncSession

    async def count_by_status(self) -> Mapping[TicketStatus, int]:
        statement = select(TicketModel.status, func.count(TicketModel.id)).group_by(
            TicketModel.status
        )
        result = await self.session.execute(statement)
        return {status: count for status, count in result.all()}

    async def count_active_tickets_per_operator(self) -> Sequence[OperatorTicketLoadRecord]:
        statement = (
            select(Operator.id, Operator.display_name, func.count(TicketModel.id))
            .join(TicketModel, TicketModel.assigned_operator_id == Operator.id)
            .where(TicketModel.status != TicketStatus.CLOSED)
            .group_by(Operator.id, Operator.display_name)
            .order_by(
                func.count(TicketModel.id).desc(),
                Operator.display_name.asc(),
                Operator.id.asc(),
            )
        )
        result = await self.session.execute(statement)
        return [
            OperatorTicketLoadRow(
                operator_id=operator_id,
                display_name=display_name,
                ticket_count=ticket_count,
            )
            for operator_id, display_name, ticket_count in result.all()
        ]

    async def count_created_tickets(self, *, since: datetime | None = None) -> int:
        statement = select(func.count(TicketModel.id))
        if since is not None:
            statement = statement.where(TicketModel.created_at >= since)
        result = await self.session.execute(statement)
        return int(result.scalar_one_or_none() or 0)

    async def count_closed_tickets(self, *, since: datetime | None = None) -> int:
        statement = select(func.count(TicketModel.id)).where(
            TicketModel.status == TicketStatus.CLOSED,
            TicketModel.closed_at.is_not(None),
        )
        if since is not None:
            statement = statement.where(TicketModel.closed_at >= since)
        result = await self.session.execute(statement)
        return int(result.scalar_one_or_none() or 0)

    async def get_average_first_response_time_seconds(
        self,
        *,
        since: datetime | None = None,
    ) -> float | None:
        statement = select(
            func.avg(func.extract("epoch", TicketModel.first_response_at - TicketModel.created_at))
        ).where(
            TicketModel.first_response_at.is_not(None),
            TicketModel.first_response_at >= TicketModel.created_at,
        )
        if since is not None:
            statement = statement.where(TicketModel.first_response_at >= since)
        result = await self.session.execute(statement)
        average_seconds = result.scalar_one_or_none()
        return None if average_seconds is None else float(average_seconds)

    async def get_average_resolution_time_seconds(
        self,
        *,
        since: datetime | None = None,
    ) -> float | None:
        statement = select(
            func.avg(func.extract("epoch", TicketModel.closed_at - TicketModel.created_at))
        ).where(
            TicketModel.status == TicketStatus.CLOSED,
            TicketModel.closed_at.is_not(None),
            TicketModel.closed_at >= TicketModel.created_at,
        )
        if since is not None:
            statement = statement.where(TicketModel.closed_at >= since)
        result = await self.session.execute(statement)
        average_seconds = result.scalar_one_or_none()
        return None if average_seconds is None else float(average_seconds)

    async def count_feedback_submissions(self, *, since: datetime | None = None) -> int:
        statement = select(func.count(TicketFeedback.id))
        if since is not None:
            statement = statement.where(TicketFeedback.submitted_at >= since)
        result = await self.session.execute(statement)
        return int(result.scalar_one_or_none() or 0)

    async def get_average_feedback_rating(self, *, since: datetime | None = None) -> float | None:
        statement = select(func.avg(TicketFeedback.rating))
        if since is not None:
            statement = statement.where(TicketFeedback.submitted_at >= since)
        result = await self.session.execute(statement)
        average_rating = result.scalar_one_or_none()
        return None if average_rating is None else float(average_rating)

    async def get_feedback_rating_distribution(
        self,
        *,
        since: datetime | None = None,
    ) -> Sequence[RatingDistributionRow]:
        statement = select(TicketFeedback.rating, func.count(TicketFeedback.id)).group_by(
            TicketFeedback.rating
        )
        if since is not None:
            statement = statement.where(TicketFeedback.submitted_at >= since)
        statement = statement.order_by(TicketFeedback.rating.desc())
        result = await self.session.execute(statement)
        return [
            RatingDistributionRow(rating=rating, count=count)
            for rating, count in result.all()
        ]

    async def list_closed_ticket_stats_by_operator(
        self,
        *,
        since: datetime | None = None,
    ) -> Sequence[OperatorClosureStatsRow]:
        statement = (
            select(
                Operator.id,
                Operator.display_name,
                func.count(TicketModel.id),
                func.avg(
                    func.extract("epoch", TicketModel.first_response_at - TicketModel.created_at)
                ),
                func.avg(func.extract("epoch", TicketModel.closed_at - TicketModel.created_at)),
                func.avg(TicketFeedback.rating),
                func.count(TicketFeedback.id),
            )
            .join(TicketModel, TicketModel.assigned_operator_id == Operator.id)
            .join(TicketFeedback, TicketFeedback.ticket_id == TicketModel.id, isouter=True)
            .where(
                TicketModel.status == TicketStatus.CLOSED,
                TicketModel.closed_at.is_not(None),
            )
            .group_by(Operator.id, Operator.display_name)
            .order_by(
                func.count(TicketModel.id).desc(),
                Operator.display_name.asc(),
                Operator.id.asc(),
            )
        )
        if since is not None:
            statement = statement.where(TicketModel.closed_at >= since)
        result = await self.session.execute(statement)
        return [
            OperatorClosureStatsRow(
                operator_id=operator_id,
                display_name=display_name,
                closed_ticket_count=closed_ticket_count,
                average_first_response_time_seconds=(
                    None if first_response is None else float(first_response)
                ),
                average_resolution_time_seconds=(
                    None if resolution is None else float(resolution)
                ),
                average_satisfaction=None if satisfaction is None else float(satisfaction),
                feedback_count=feedback_count,
            )
            for (
                operator_id,
                display_name,
                closed_ticket_count,
                first_response,
                resolution,
                satisfaction,
                feedback_count,
            ) in result.all()
        ]

    async def list_created_ticket_counts_by_category(
        self,
        *,
        since: datetime | None = None,
    ) -> Sequence[CategoryTicketCountRow]:
        statement = (
            select(TicketCategory.id, TicketCategory.title, func.count(TicketModel.id))
            .select_from(TicketModel)
            .join(TicketCategory, TicketModel.category_id == TicketCategory.id, isouter=True)
            .group_by(TicketCategory.id, TicketCategory.title)
            .order_by(desc(func.count(TicketModel.id)), TicketCategory.title.asc())
        )
        if since is not None:
            statement = statement.where(TicketModel.created_at >= since)
        result = await self.session.execute(statement)
        return [
            CategoryTicketCountRow(
                category_id=category_id,
                category_title=category_title,
                ticket_count=ticket_count,
            )
            for category_id, category_title, ticket_count in result.all()
        ]

    async def list_open_ticket_counts_by_category(self) -> Sequence[CategoryTicketCountRow]:
        statement = (
            select(TicketCategory.id, TicketCategory.title, func.count(TicketModel.id))
            .select_from(TicketModel)
            .join(TicketCategory, TicketModel.category_id == TicketCategory.id, isouter=True)
            .where(TicketModel.status != TicketStatus.CLOSED)
            .group_by(TicketCategory.id, TicketCategory.title)
            .order_by(desc(func.count(TicketModel.id)), TicketCategory.title.asc())
        )
        result = await self.session.execute(statement)
        return [
            CategoryTicketCountRow(
                category_id=category_id,
                category_title=category_title,
                ticket_count=ticket_count,
            )
            for category_id, category_title, ticket_count in result.all()
        ]

    async def list_closed_ticket_counts_by_category(
        self,
        *,
        since: datetime | None = None,
    ) -> Sequence[CategoryTicketCountRow]:
        statement = (
            select(TicketCategory.id, TicketCategory.title, func.count(TicketModel.id))
            .select_from(TicketModel)
            .join(TicketCategory, TicketModel.category_id == TicketCategory.id, isouter=True)
            .where(
                TicketModel.status == TicketStatus.CLOSED,
                TicketModel.closed_at.is_not(None),
            )
            .group_by(TicketCategory.id, TicketCategory.title)
            .order_by(desc(func.count(TicketModel.id)), TicketCategory.title.asc())
        )
        if since is not None:
            statement = statement.where(TicketModel.closed_at >= since)
        result = await self.session.execute(statement)
        return [
            CategoryTicketCountRow(
                category_id=category_id,
                category_title=category_title,
                ticket_count=ticket_count,
            )
            for category_id, category_title, ticket_count in result.all()
        ]

    async def list_feedback_stats_by_category(
        self,
        *,
        since: datetime | None = None,
    ) -> Sequence[CategoryFeedbackStatsRow]:
        statement = (
            select(
                TicketCategory.id,
                TicketCategory.title,
                func.avg(TicketFeedback.rating),
                func.count(TicketFeedback.id),
            )
            .select_from(TicketFeedback)
            .join(TicketModel, TicketFeedback.ticket_id == TicketModel.id)
            .join(TicketCategory, TicketModel.category_id == TicketCategory.id, isouter=True)
            .group_by(TicketCategory.id, TicketCategory.title)
            .order_by(desc(func.avg(TicketFeedback.rating)), desc(func.count(TicketFeedback.id)))
        )
        if since is not None:
            statement = statement.where(TicketFeedback.submitted_at >= since)
        result = await self.session.execute(statement)
        return [
            CategoryFeedbackStatsRow(
                category_id=category_id,
                category_title=category_title,
                average_satisfaction=None if rating is None else float(rating),
                feedback_count=feedback_count,
            )
            for category_id, category_title, rating, feedback_count in result.all()
        ]

    async def count_sla_breaches(self, *, since: datetime | None = None) -> Mapping[str, int]:
        statement = select(TicketEvent.event_type, func.count(TicketEvent.id)).where(
            TicketEvent.event_type.in_(
                (
                    TicketEventType.SLA_BREACHED_FIRST_RESPONSE,
                    TicketEventType.SLA_BREACHED_RESOLUTION,
                )
            )
        )
        if since is not None:
            statement = statement.where(TicketEvent.created_at >= since)
        statement = statement.group_by(TicketEvent.event_type)
        result = await self.session.execute(statement)
        return {event_type.value: count for event_type, count in result.all()}

    async def list_sla_breach_counts_by_category(
        self,
        *,
        since: datetime | None = None,
    ) -> Sequence[SLABreachCountRow]:
        statement = (
            select(TicketCategory.id, TicketCategory.title, func.count(TicketEvent.id))
            .select_from(TicketEvent)
            .join(TicketModel, TicketEvent.ticket_id == TicketModel.id)
            .join(TicketCategory, TicketModel.category_id == TicketCategory.id, isouter=True)
            .where(
                TicketEvent.event_type.in_(
                    (
                        TicketEventType.SLA_BREACHED_FIRST_RESPONSE,
                        TicketEventType.SLA_BREACHED_RESOLUTION,
                    )
                )
            )
            .group_by(TicketCategory.id, TicketCategory.title)
            .order_by(desc(func.count(TicketEvent.id)), TicketCategory.title.asc())
        )
        if since is not None:
            statement = statement.where(TicketEvent.created_at >= since)
        result = await self.session.execute(statement)
        return [
            SLABreachCountRow(
                category_id=category_id,
                category_title=category_title,
                breach_count=breach_count,
            )
            for category_id, category_title, breach_count in result.all()
        ]
