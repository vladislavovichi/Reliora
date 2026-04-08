from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
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

from domain.enums.tickets import (
    TicketEventType,
    TicketMessageSenderType,
    TicketPriority,
    TicketStatus,
)
from infrastructure.db.base import Base
from infrastructure.db.models.mixins import CreatedAtMixin, TimestampMixin, enum_values

if TYPE_CHECKING:
    from infrastructure.db.models.catalog import Tag, TicketCategory
    from infrastructure.db.models.operator import Operator


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
    category_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("ticket_categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    assigned_operator_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("operators.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    first_response_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    assigned_operator: Mapped[Operator | None] = relationship(
        back_populates="assigned_tickets",
        foreign_keys=[assigned_operator_id],
    )
    category: Mapped[TicketCategory | None] = relationship(back_populates="tickets")
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
    sender_operator: Mapped[Operator | None] = relationship(back_populates="sent_messages")


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
