from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Enum, Identity, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from domain.enums.tickets import TicketPriority
from infrastructure.db.base import Base
from infrastructure.db.models.mixins import CreatedAtMixin, enum_values

if TYPE_CHECKING:
    from infrastructure.db.models.ticket import Ticket, TicketTag


class Macro(CreatedAtMixin, Base):
    __tablename__ = "macros"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    title: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)


class SLAPolicy(Base):
    __tablename__ = "sla_policies"
    __table_args__ = (
        CheckConstraint("first_response_minutes > 0", name="first_response_minutes_positive"),
        CheckConstraint("resolution_minutes > 0", name="resolution_minutes_positive"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    first_response_minutes: Mapped[int] = mapped_column(nullable=False)
    resolution_minutes: Mapped[int] = mapped_column(nullable=False)
    priority: Mapped[TicketPriority | None] = mapped_column(
        Enum(
            TicketPriority,
            name="ticket_priority",
            values_callable=enum_values,
        ),
        nullable=True,
        index=True,
    )


class Tag(CreatedAtMixin, Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    ticket_tags: Mapped[list[TicketTag]] = relationship(
        back_populates="tag",
        cascade="all, delete-orphan",
    )


class TicketCategory(Base):
    __tablename__ = "ticket_categories"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    sort_order: Mapped[int] = mapped_column(nullable=False, default=100, server_default="100")

    tickets: Mapped[list[Ticket]] = relationship(back_populates="category")
