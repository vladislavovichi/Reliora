from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.ticket import (
    Ticket as TicketEntity,
)
from domain.entities.ticket import (
    TicketAttachmentDetails,
    TicketDetails,
    TicketInternalNoteDetails,
    TicketMessageDetails,
)
from domain.enums.tickets import TicketAttachmentKind, TicketMessageSenderType, TicketStatus
from infrastructure.db.models.catalog import Tag, TicketCategory
from infrastructure.db.models.operator import Operator
from infrastructure.db.models.ticket import (
    Ticket as TicketModel,
)
from infrastructure.db.models.ticket import (
    TicketInternalNote,
    TicketMessage,
    TicketTag,
)
from infrastructure.db.repositories.base import apply_queue_ordering


class SqlAlchemyTicketReadRepository:
    session: AsyncSession

    async def get_by_public_id(self, public_id: UUID) -> TicketEntity | None:
        result = await self.session.execute(
            select(TicketModel).where(TicketModel.public_id == public_id)
        )
        return cast(TicketEntity | None, result.scalar_one_or_none())

    async def get_details_by_public_id(self, public_id: UUID) -> TicketDetails | None:
        ticket = await self.get_by_public_id(public_id)
        if ticket is None or ticket.id is None:
            return None

        (
            assigned_operator_name,
            assigned_operator_telegram_user_id,
        ) = await self._get_assigned_operator_details(ticket.assigned_operator_id)
        category_code, category_title = await self._get_category_details(ticket.category_id)
        (
            last_message_text,
            last_message_sender_type,
            last_message_attachment,
        ) = await self._get_last_message(ticket.id)
        tags = await self._list_ticket_tags(ticket.id)
        message_history = await self._list_ticket_messages(ticket.id)
        internal_notes = await self._list_ticket_internal_notes(ticket.id)

        return TicketDetails(
            id=ticket.id,
            public_id=ticket.public_id,
            client_chat_id=ticket.client_chat_id,
            status=ticket.status,
            priority=ticket.priority,
            subject=ticket.subject,
            assigned_operator_id=ticket.assigned_operator_id,
            assigned_operator_name=assigned_operator_name,
            assigned_operator_telegram_user_id=assigned_operator_telegram_user_id,
            created_at=ticket.created_at,
            updated_at=ticket.updated_at,
            first_response_at=ticket.first_response_at,
            closed_at=ticket.closed_at,
            category_id=ticket.category_id,
            category_code=category_code,
            category_title=category_title,
            tags=tags,
            last_message_text=last_message_text,
            last_message_sender_type=last_message_sender_type,
            last_message_attachment=last_message_attachment,
            message_history=message_history,
            internal_notes=internal_notes,
        )

    async def get_active_by_client_chat_id(self, client_chat_id: int) -> TicketEntity | None:
        statement = (
            select(TicketModel)
            .where(TicketModel.client_chat_id == client_chat_id)
            .where(TicketModel.status != TicketStatus.CLOSED)
            .order_by(desc(TicketModel.updated_at), desc(TicketModel.created_at))
            .limit(1)
        )
        result = await self.session.execute(statement)
        return cast(TicketEntity | None, result.scalar_one_or_none())

    async def get_next_queued_ticket(
        self,
        *,
        prioritize_priority: bool = False,
    ) -> TicketEntity | None:
        statement = apply_queue_ordering(
            select(TicketModel).where(TicketModel.status == TicketStatus.QUEUED).limit(1),
            prioritize_priority=prioritize_priority,
        )
        result = await self.session.execute(statement)
        return cast(TicketEntity | None, result.scalar_one_or_none())

    async def list_queued_tickets(
        self,
        *,
        limit: int | None = None,
        prioritize_priority: bool = False,
    ) -> Sequence[TicketEntity]:
        statement = apply_queue_ordering(
            select(TicketModel).where(TicketModel.status == TicketStatus.QUEUED),
            prioritize_priority=prioritize_priority,
        )
        if limit is not None:
            statement = statement.limit(limit)

        result = await self.session.execute(statement)
        return cast(Sequence[TicketEntity], result.scalars().all())

    async def list_open_tickets(self, *, limit: int | None = None) -> Sequence[TicketEntity]:
        statement = (
            select(TicketModel)
            .where(TicketModel.status != TicketStatus.CLOSED)
            .order_by(TicketModel.updated_at.asc(), TicketModel.id.asc())
        )
        if limit is not None:
            statement = statement.limit(limit)

        result = await self.session.execute(statement)
        return cast(Sequence[TicketEntity], result.scalars().all())

    async def list_open_tickets_for_operator(
        self,
        *,
        operator_telegram_user_id: int,
        limit: int | None = None,
    ) -> Sequence[TicketEntity]:
        statement = (
            select(TicketModel)
            .join(Operator, TicketModel.assigned_operator_id == Operator.id)
            .where(TicketModel.status != TicketStatus.CLOSED)
            .where(Operator.telegram_user_id == operator_telegram_user_id)
            .order_by(TicketModel.updated_at.desc(), TicketModel.id.desc())
        )
        if limit is not None:
            statement = statement.limit(limit)

        result = await self.session.execute(statement)
        return cast(Sequence[TicketEntity], result.scalars().all())

    async def _get_assigned_operator_details(
        self,
        operator_id: int | None,
    ) -> tuple[str | None, int | None]:
        if operator_id is None:
            return None, None

        result = await self.session.execute(
            select(Operator.display_name, Operator.telegram_user_id).where(
                Operator.id == operator_id
            )
        )
        row = result.first()
        if row is None:
            return None, None
        return cast(str | None, row[0]), cast(int | None, row[1])

    async def _get_last_message(
        self,
        ticket_id: int,
    ) -> tuple[
        str | None,
        TicketMessageSenderType | None,
        TicketAttachmentDetails | None,
    ]:
        statement = (
            select(
                TicketMessage.text,
                TicketMessage.sender_type,
                TicketMessage.attachment_kind,
                TicketMessage.attachment_file_id,
                TicketMessage.attachment_file_unique_id,
                TicketMessage.attachment_filename,
                TicketMessage.attachment_mime_type,
                TicketMessage.attachment_storage_path,
            )
            .where(TicketMessage.ticket_id == ticket_id)
            .order_by(desc(TicketMessage.created_at), desc(TicketMessage.id))
            .limit(1)
        )
        result = await self.session.execute(statement)
        row = result.first()
        if row is None:
            return None, None, None
        return (
            cast(str | None, row[0]),
            cast(TicketMessageSenderType, row[1]),
            _build_attachment_details(
                kind=cast(TicketAttachmentKind | None, _row_value(row, 2)),
                file_id=cast(str | None, _row_value(row, 3)),
                file_unique_id=cast(str | None, _row_value(row, 4)),
                filename=cast(str | None, _row_value(row, 5)),
                mime_type=cast(str | None, _row_value(row, 6)),
                storage_path=cast(str | None, _row_value(row, 7)),
            ),
        )

    async def _get_category_details(self, category_id: int | None) -> tuple[str | None, str | None]:
        if category_id is None:
            return None, None

        result = await self.session.execute(
            select(TicketCategory.code, TicketCategory.title).where(
                TicketCategory.id == category_id
            )
        )
        row = result.first()
        if row is None:
            return None, None
        return cast(str | None, row[0]), cast(str | None, row[1])

    async def _list_ticket_tags(self, ticket_id: int) -> tuple[str, ...]:
        statement = (
            select(Tag.name)
            .join(TicketTag, TicketTag.tag_id == Tag.id)
            .where(TicketTag.ticket_id == ticket_id)
            .order_by(Tag.name.asc(), Tag.id.asc())
        )
        result = await self.session.execute(statement)
        return tuple(cast(list[str], result.scalars().all()))

    async def _list_ticket_messages(self, ticket_id: int) -> tuple[TicketMessageDetails, ...]:
        statement = (
            select(
                TicketMessage.telegram_message_id,
                TicketMessage.sender_type,
                TicketMessage.sender_operator_id,
                Operator.display_name,
                TicketMessage.text,
                TicketMessage.attachment_kind,
                TicketMessage.attachment_file_id,
                TicketMessage.attachment_file_unique_id,
                TicketMessage.attachment_filename,
                TicketMessage.attachment_mime_type,
                TicketMessage.attachment_storage_path,
                TicketMessage.created_at,
            )
            .join(Operator, TicketMessage.sender_operator_id == Operator.id, isouter=True)
            .where(TicketMessage.ticket_id == ticket_id)
            .order_by(TicketMessage.created_at.asc(), TicketMessage.id.asc())
        )
        result = await self.session.execute(statement)
        return tuple(
            TicketMessageDetails(
                telegram_message_id=cast(int, row[0]),
                sender_type=cast(TicketMessageSenderType, row[1]),
                sender_operator_id=cast(int | None, row[2]),
                sender_operator_name=cast(str | None, row[3]),
                text=cast(str | None, row[4]),
                attachment=_build_attachment_details(
                    kind=cast(TicketAttachmentKind | None, _row_value(row, 5)),
                    file_id=cast(str | None, _row_value(row, 6)),
                    file_unique_id=cast(str | None, _row_value(row, 7)),
                    filename=cast(str | None, _row_value(row, 8)),
                    mime_type=cast(str | None, _row_value(row, 9)),
                    storage_path=cast(str | None, _row_value(row, 10)),
                ),
                created_at=cast(datetime, _row_value(row, 11, _row_value(row, 10))),
            )
            for row in result.all()
        )

    async def _list_ticket_internal_notes(
        self,
        ticket_id: int,
    ) -> tuple[TicketInternalNoteDetails, ...]:
        statement = (
            select(
                TicketInternalNote.id,
                TicketInternalNote.author_operator_id,
                Operator.display_name,
                TicketInternalNote.text,
                TicketInternalNote.created_at,
            )
            .join(Operator, TicketInternalNote.author_operator_id == Operator.id)
            .where(TicketInternalNote.ticket_id == ticket_id)
            .order_by(TicketInternalNote.created_at.asc(), TicketInternalNote.id.asc())
        )
        result = await self.session.execute(statement)
        return tuple(
            TicketInternalNoteDetails(
                id=cast(int, row[0]),
                author_operator_id=cast(int, row[1]),
                author_operator_name=cast(str | None, row[2]),
                text=cast(str, row[3]),
                created_at=cast(datetime, row[4]),
            )
            for row in result.all()
        )


def _build_attachment_details(
    *,
    kind: TicketAttachmentKind | None,
    file_id: str | None,
    file_unique_id: str | None,
    filename: str | None,
    mime_type: str | None,
    storage_path: str | None,
) -> TicketAttachmentDetails | None:
    if kind is None or file_id is None:
        return None
    return TicketAttachmentDetails(
        kind=kind,
        telegram_file_id=file_id,
        telegram_file_unique_id=file_unique_id,
        filename=filename,
        mime_type=mime_type,
        storage_path=storage_path,
    )


def _row_value(row: object, index: int, default: object = None) -> object:
    try:
        return cast(object, row[index])  # type: ignore[index]
    except (IndexError, TypeError):
        return default
