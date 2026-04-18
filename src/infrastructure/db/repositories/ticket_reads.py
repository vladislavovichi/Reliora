from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import SQLCoreOperations
from sqlalchemy.sql.roles import TypedColumnsClauseRole
from sqlalchemy.sql.selectable import ScalarSelect

from domain.entities.ticket import (
    TicketAttachmentDetails,
    TicketDetails,
    TicketHistoryEntry,
    TicketInternalNoteDetails,
    TicketMessageDetails,
)
from domain.enums.tickets import TicketMessageSenderType, TicketStatus
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
from infrastructure.db.repositories.ticket_message_mapping import (
    build_attachment_details,
    build_attachment_from_message,
    build_ticket_message_details,
)


class SqlAlchemyTicketReadRepository:
    session: AsyncSession

    async def get_by_public_id(self, public_id: UUID) -> TicketModel | None:
        result = await self.session.execute(
            select(TicketModel).where(TicketModel.public_id == public_id)
        )
        return result.scalar_one_or_none()

    async def get_details_by_public_id(self, public_id: UUID) -> TicketDetails | None:
        ticket = await self.get_by_public_id(public_id)
        if ticket is None or ticket.id is None:
            return None

        (
            assigned_operator_name,
            assigned_operator_telegram_user_id,
            assigned_operator_username,
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
            assigned_operator_username=assigned_operator_username,
            created_at=ticket.created_at,
            updated_at=ticket.updated_at,
            first_response_at=ticket.first_response_at,
            closed_at=ticket.closed_at,
            category_id=ticket.category_id,
            category_code=category_code,
            category_title=category_title,
            sentiment=ticket.sentiment,
            sentiment_confidence=ticket.sentiment_confidence,
            sentiment_reason=ticket.sentiment_reason,
            sentiment_detected_at=ticket.sentiment_detected_at,
            tags=tags,
            last_message_text=last_message_text,
            last_message_sender_type=last_message_sender_type,
            last_message_attachment=last_message_attachment,
            message_history=message_history,
            internal_notes=internal_notes,
        )

    async def get_active_by_client_chat_id(self, client_chat_id: int) -> TicketModel | None:
        statement = (
            select(TicketModel)
            .where(TicketModel.client_chat_id == client_chat_id)
            .where(TicketModel.status != TicketStatus.CLOSED)
            .order_by(desc(TicketModel.updated_at), desc(TicketModel.created_at))
            .limit(1)
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_next_queued_ticket(
        self,
        *,
        prioritize_priority: bool = False,
    ) -> TicketModel | None:
        statement = apply_queue_ordering(
            select(TicketModel).where(TicketModel.status == TicketStatus.QUEUED).limit(1),
            prioritize_priority=prioritize_priority,
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def list_queued_tickets(
        self,
        *,
        limit: int | None = None,
        prioritize_priority: bool = False,
    ) -> tuple[TicketModel, ...]:
        statement = apply_queue_ordering(
            select(TicketModel).where(TicketModel.status == TicketStatus.QUEUED),
            prioritize_priority=prioritize_priority,
        )
        if limit is not None:
            statement = statement.limit(limit)

        result = await self.session.execute(statement)
        return tuple(result.scalars().all())

    async def list_open_tickets(self, *, limit: int | None = None) -> tuple[TicketModel, ...]:
        statement = (
            select(TicketModel)
            .where(TicketModel.status != TicketStatus.CLOSED)
            .order_by(TicketModel.updated_at.asc(), TicketModel.id.asc())
        )
        if limit is not None:
            statement = statement.limit(limit)

        result = await self.session.execute(statement)
        return tuple(result.scalars().all())

    async def list_open_tickets_for_operator(
        self,
        *,
        operator_telegram_user_id: int,
        limit: int | None = None,
    ) -> tuple[TicketModel, ...]:
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
        return tuple(result.scalars().all())

    async def list_closed_tickets(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> Sequence[TicketHistoryEntry]:
        first_client_message_text = _first_client_message_scalar(TicketMessage.text)
        first_client_attachment_kind = _first_client_message_scalar(TicketMessage.attachment_kind)
        first_client_attachment_file_id = _first_client_message_scalar(
            TicketMessage.attachment_file_id
        )
        first_client_attachment_file_unique_id = _first_client_message_scalar(
            TicketMessage.attachment_file_unique_id
        )
        first_client_attachment_filename = _first_client_message_scalar(
            TicketMessage.attachment_filename
        )
        first_client_attachment_mime_type = _first_client_message_scalar(
            TicketMessage.attachment_mime_type
        )
        first_client_attachment_storage_path = _first_client_message_scalar(
            TicketMessage.attachment_storage_path
        )
        statement = (
            select(
                TicketModel.public_id,
                TicketModel.status,
                TicketModel.subject,
                TicketModel.created_at,
                TicketModel.closed_at,
                TicketCategory.id,
                TicketCategory.code,
                TicketCategory.title,
                first_client_message_text.label("first_client_message_text"),
                first_client_attachment_kind.label("first_client_attachment_kind"),
                first_client_attachment_file_id.label("first_client_attachment_file_id"),
                first_client_attachment_file_unique_id.label(
                    "first_client_attachment_file_unique_id"
                ),
                first_client_attachment_filename.label("first_client_attachment_filename"),
                first_client_attachment_mime_type.label("first_client_attachment_mime_type"),
                first_client_attachment_storage_path.label("first_client_attachment_storage_path"),
            )
            .join(TicketCategory, TicketModel.category_id == TicketCategory.id, isouter=True)
            .where(TicketModel.status == TicketStatus.CLOSED)
            .order_by(
                desc(TicketModel.closed_at),
                desc(TicketModel.updated_at),
                desc(TicketModel.id),
            )
            .offset(offset)
        )
        if limit is not None:
            statement = statement.limit(limit)

        result = await self.session.execute(statement)
        return tuple(
            TicketHistoryEntry(
                public_id=public_id,
                status=status,
                subject=subject,
                created_at=created_at,
                closed_at=closed_at,
                category_id=category_id,
                category_code=category_code,
                category_title=category_title,
                first_client_message_text=first_client_message_text,
                first_client_message_attachment=build_attachment_details(
                    kind=first_client_attachment_kind,
                    file_id=first_client_attachment_file_id,
                    file_unique_id=first_client_attachment_file_unique_id,
                    filename=first_client_attachment_filename,
                    mime_type=first_client_attachment_mime_type,
                    storage_path=first_client_attachment_storage_path,
                ),
            )
            for (
                public_id,
                status,
                subject,
                created_at,
                closed_at,
                category_id,
                category_code,
                category_title,
                first_client_message_text,
                first_client_attachment_kind,
                first_client_attachment_file_id,
                first_client_attachment_file_unique_id,
                first_client_attachment_filename,
                first_client_attachment_mime_type,
                first_client_attachment_storage_path,
            ) in result.all()
        )

    async def _get_assigned_operator_details(
        self,
        operator_id: int | None,
    ) -> tuple[str | None, int | None, str | None]:
        if operator_id is None:
            return None, None, None

        result = await self.session.execute(
            select(Operator.display_name, Operator.telegram_user_id, Operator.username).where(
                Operator.id == operator_id
            )
        )
        row = result.first()
        if row is None:
            return None, None, None
        assigned_operator_name, assigned_operator_telegram_user_id, assigned_operator_username = row
        return (
            assigned_operator_name,
            assigned_operator_telegram_user_id,
            assigned_operator_username,
        )

    async def _get_last_message(
        self,
        ticket_id: int,
    ) -> tuple[
        str | None,
        TicketMessageSenderType | None,
        TicketAttachmentDetails | None,
    ]:
        statement = (
            select(TicketMessage)
            .where(TicketMessage.ticket_id == ticket_id)
            .order_by(desc(TicketMessage.created_at), desc(TicketMessage.id))
            .limit(1)
        )
        result = await self.session.execute(statement)
        message = result.scalar_one_or_none()
        if message is None:
            return None, None, None
        return (
            message.text,
            message.sender_type,
            build_attachment_from_message(message),
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
        category_code, category_title = row
        return category_code, category_title

    async def _list_ticket_tags(self, ticket_id: int) -> tuple[str, ...]:
        statement = (
            select(Tag.name)
            .join(TicketTag, TicketTag.tag_id == Tag.id)
            .where(TicketTag.ticket_id == ticket_id)
            .order_by(Tag.name.asc(), Tag.id.asc())
        )
        result = await self.session.execute(statement)
        return tuple(result.scalars().all())

    async def _list_ticket_messages(self, ticket_id: int) -> tuple[TicketMessageDetails, ...]:
        statement = (
            select(TicketMessage, Operator.display_name)
            .join(Operator, TicketMessage.sender_operator_id == Operator.id, isouter=True)
            .where(TicketMessage.ticket_id == ticket_id)
            .order_by(TicketMessage.created_at.asc(), TicketMessage.id.asc())
        )
        result = await self.session.execute(statement)
        return tuple(
            build_ticket_message_details(
                message,
                sender_operator_name=sender_operator_name,
            )
            for message, sender_operator_name in result.all()
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
                id=note_id,
                author_operator_id=author_operator_id,
                author_operator_name=author_operator_name,
                text=text,
                created_at=created_at,
            )
            for (
                note_id,
                author_operator_id,
                author_operator_name,
                text,
                created_at,
            ) in result.all()
        )


def _first_client_message_scalar[T](
    column: TypedColumnsClauseRole[T] | SQLCoreOperations[T],
) -> ScalarSelect[T]:
    return (
        select(column)
        .where(TicketMessage.ticket_id == TicketModel.id)
        .where(TicketMessage.sender_type == TicketMessageSenderType.CLIENT)
        .order_by(TicketMessage.created_at.asc(), TicketMessage.id.asc())
        .limit(1)
        .scalar_subquery()
    )
