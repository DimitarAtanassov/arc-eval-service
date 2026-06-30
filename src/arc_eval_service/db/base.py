"""SQLAlchemy declarative base shared by every ORM model.

``Base.metadata`` is the Alembic ``target_metadata``; the migration env imports
:mod:`arc_eval_service.db.models` so every table registers against it.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""
