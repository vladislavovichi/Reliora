"""Database primitives and SQLAlchemy scaffolding."""

from infrastructure.db.base import Base, metadata
from infrastructure.db.session import (
    build_engine,
    build_session_factory,
    dispose_engine,
    get_engine,
    get_session_factory,
    session_scope,
)

__all__ = [
    "Base",
    "build_engine",
    "build_session_factory",
    "dispose_engine",
    "get_engine",
    "get_session_factory",
    "metadata",
    "session_scope",
]
