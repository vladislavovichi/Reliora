from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Identity, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infrastructure.db.base import Base
from infrastructure.db.models.mixins import CreatedAtMixin

if TYPE_CHECKING:
    from infrastructure.db.models.ticket import Ticket, TicketMessage


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
    sent_messages: Mapped[list[TicketMessage]] = relationship(back_populates="sender_operator")
