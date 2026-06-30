"""SQLAlchemy declarative base.

A single :class:`Base` shared by every ORM row across the storage slices
(:mod:`arc_eval_service.storage.evaluation`, :mod:`arc_eval_service.storage.spans`).
``Base.metadata`` is the Alembic ``target_metadata``; the migration env imports
those slice modules so every table registers against it.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""
