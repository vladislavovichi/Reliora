from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.db.base import Base
from infrastructure.db.models.mixins import CreatedAtMixin, utcnow


class TicketAISummary(Base, CreatedAtMixin):
    __tablename__ = "ticket_ai_summaries"
    __table_args__ = (UniqueConstraint("ticket_id", name="uq_ticket_ai_summaries_ticket_id"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    ticket_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tickets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    short_summary: Mapped[str] = mapped_column(Text, nullable=False)
    user_goal: Mapped[str] = mapped_column(Text, nullable=False)
    actions_taken: Mapped[str] = mapped_column(Text, nullable=False)
    current_status: Mapped[str] = mapped_column(Text, nullable=False)
    model_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
        index=True,
    )
    source_ticket_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    source_message_count: Mapped[int] = mapped_column(Integer, nullable=False)
    source_internal_note_count: Mapped[int] = mapped_column(Integer, nullable=False)
