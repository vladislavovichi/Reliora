from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum as PythonEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Identity,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from domain.enums.tickets import (
    TicketEventType,
    TicketMessageSenderType,
    TicketPriority,
    TicketStatus,
)
from infrastructure.db.base import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


def enum_values(enum_cls: type[PythonEnum]) -> list[str]:
    return [member.value for member in enum_cls]


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=func.now(),
        nullable=False,
    )


class TimestampMixin(CreatedAtMixin):
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        server_default=func.now(),
        nullable=False,
    )


class Operator(CreatedAtMixin, Base):
    __tablename__ = "operators"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, nullable=False, index=True
    )
    username: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
        server_default="true",
    )

    assigned_tickets: Mapped[list[Ticket]] = relationship(
        back_populates="assigned_operator",
        foreign_keys="Ticket.assigned_operator_id",
    )
    sent_messages: Mapped[list[TicketMessage]] = relationship(
        back_populates="sender_operator"
    )


class Macro(CreatedAtMixin, Base):
    __tablename__ = "macros"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    title: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)


class SLAPolicy(Base):
    __tablename__ = "sla_policies"
    __table_args__ = (
        CheckConstraint(
            "first_response_minutes > 0", name="first_response_minutes_positive"
        ),
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


class Ticket(TimestampMixin, Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    public_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), default=uuid4, unique=True, nullable=False
    )
    client_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    status: Mapped[TicketStatus] = mapped_column(
        Enum(
            TicketStatus,
            name="ticket_status",
            values_callable=enum_values,
        ),
        nullable=False,
        default=TicketStatus.NEW,
        server_default=TicketStatus.NEW.value,
        index=True,
    )
    priority: Mapped[TicketPriority] = mapped_column(
        Enum(
            TicketPriority,
            name="ticket_priority",
            values_callable=enum_values,
        ),
        nullable=False,
        default=TicketPriority.NORMAL,
        server_default=TicketPriority.NORMAL.value,
        index=True,
    )
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    assigned_operator_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("operators.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    first_response_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    assigned_operator: Mapped[Operator | None] = relationship(
        back_populates="assigned_tickets",
        foreign_keys=[assigned_operator_id],
    )
    messages: Mapped[list[TicketMessage]] = relationship(
        back_populates="ticket",
        cascade="all, delete-orphan",
    )
    events: Mapped[list[TicketEvent]] = relationship(
        back_populates="ticket",
        cascade="all, delete-orphan",
    )
    ticket_tags: Mapped[list[TicketTag]] = relationship(
        back_populates="ticket",
        cascade="all, delete-orphan",
    )


class TicketMessage(CreatedAtMixin, Base):
    __tablename__ = "ticket_messages"
    __table_args__ = (
        CheckConstraint("length(text) > 0", name="ticket_message_text_not_empty"),
        UniqueConstraint(
            "ticket_id",
            "telegram_message_id",
            "sender_type",
            name="uq_ticket_messages_ticket_telegram_sender",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    ticket_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tickets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    telegram_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sender_type: Mapped[TicketMessageSenderType] = mapped_column(
        Enum(
            TicketMessageSenderType,
            name="ticket_message_sender_type",
            values_callable=enum_values,
        ),
        nullable=False,
    )
    sender_operator_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("operators.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)

    ticket: Mapped[Ticket] = relationship(back_populates="messages")
    sender_operator: Mapped[Operator | None] = relationship(
        back_populates="sent_messages"
    )


class TicketEvent(CreatedAtMixin, Base):
    __tablename__ = "ticket_events"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    ticket_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tickets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[TicketEventType] = mapped_column(
        Enum(
            TicketEventType,
            name="ticket_event_type",
            values_callable=enum_values,
        ),
        nullable=False,
        index=True,
    )
    payload_json: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)

    ticket: Mapped[Ticket] = relationship(back_populates="events")


class Tag(CreatedAtMixin, Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    ticket_tags: Mapped[list[TicketTag]] = relationship(
        back_populates="tag",
        cascade="all, delete-orphan",
    )


class TicketTag(Base):
    __tablename__ = "ticket_tags"

    ticket_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tickets.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tag_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    )

    ticket: Mapped[Ticket] = relationship(back_populates="ticket_tags")
    tag: Mapped[Tag] = relationship(back_populates="ticket_tags")
