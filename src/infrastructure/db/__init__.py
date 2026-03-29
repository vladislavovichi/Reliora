"""Database primitives and SQLAlchemy scaffolding."""

from infrastructure.db.base import Base, metadata
from infrastructure.db.repositories import (
    SqlAlchemyOperatorRepository,
    SqlAlchemyTagRepository,
    SqlAlchemyTicketEventRepository,
    SqlAlchemyTicketMessageRepository,
    SqlAlchemyTicketRepository,
)
from infrastructure.db.session import (
    build_engine,
    build_session_factory,
    dispose_engine,
    get_engine,
    get_session_factory,
    provide_session,
    session_scope,
)

__all__ = [
    "Base",
    "SqlAlchemyOperatorRepository",
    "SqlAlchemyTagRepository",
    "SqlAlchemyTicketEventRepository",
    "SqlAlchemyTicketMessageRepository",
    "SqlAlchemyTicketRepository",
    "build_engine",
    "build_session_factory",
    "dispose_engine",
    "get_engine",
    "get_session_factory",
    "metadata",
    "provide_session",
    "session_scope",
]
