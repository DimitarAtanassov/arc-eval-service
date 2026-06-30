"""Persistence for prompt templates, deduplicated on content hash.

The same template arrives on many requests, so it is stored once: a sha256 of the
content backs a unique index, and writes are idempotent upserts. The hash helper
is pure and unit-tests without a database.
"""

from __future__ import annotations

import hashlib
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from arc_eval_service.db.models import PromptTemplateRow
from arc_eval_service.db.repositories.base import BaseRepository


def content_hash(template: str) -> str:
    """Return the sha256 hex digest of a template's content (pure)."""
    return hashlib.sha256(template.encode("utf-8")).hexdigest()


class PromptTemplateRepository(BaseRepository):
    """Stores prompt templates, one row per distinct content."""

    async def get_or_create(self, template: str) -> str:
        """Return the id of the row for ``template``, inserting it when new."""
        digest = content_hash(template)
        insert_stmt = (
            insert(PromptTemplateRow)
            .values(id=str(uuid4()), template=template, content_hash=digest)
            .on_conflict_do_nothing(index_elements=[PromptTemplateRow.content_hash])
        )
        select_stmt = select(PromptTemplateRow.id).where(
            PromptTemplateRow.content_hash == digest
        )
        async with self._transaction() as session:
            await session.execute(insert_stmt)
            return (await session.execute(select_stmt)).scalar_one()
