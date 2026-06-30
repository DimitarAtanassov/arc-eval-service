"""Persistence for eval-ready cases.

The :class:`CaseRepository` plus its pure row <-> domain mappers live together so
"how is a case stored?" is answered in one file. The mappers are pure functions
and unit-test without a live database.
"""

from __future__ import annotations

from sqlalchemy import select

from arc_eval_service.core.errors import NotFoundError
from arc_eval_service.db.models import CaseRow
from arc_eval_service.db.repositories.base import BaseRepository
from arc_eval_service.evaluation.schemas import EvaluationCase, StoredCase


def case_to_row(stored: StoredCase) -> CaseRow:
    case = stored.case
    return CaseRow(
        case_id=stored.case_id,
        request_id=case.request_id,
        trace_id=stored.trace_id,
        input=case.input,
        output=case.output,
        context=case.context,
        reference=case.reference,
        case_metadata=case.metadata,
        created_at=stored.created_at,
    )


def row_to_stored_case(row: CaseRow) -> StoredCase:
    return StoredCase(
        case_id=row.case_id,
        trace_id=row.trace_id,
        created_at=row.created_at,
        case=EvaluationCase(
            request_id=row.request_id,
            input=row.input,
            output=row.output,
            context=row.context,
            reference=row.reference,
            metadata=row.case_metadata,
        ),
    )


class CaseRepository(BaseRepository):
    """Persistence for eval-ready cases."""

    async def create(self, stored: StoredCase) -> None:
        async with self._transaction() as session:
            session.add(case_to_row(stored))

    async def get(self, case_id: str) -> StoredCase:
        async with self._session() as session:
            row = await session.get(CaseRow, case_id)
        if row is None:
            raise NotFoundError("case", case_id)
        return row_to_stored_case(row)

    async def list_recent(self, limit: int) -> list[StoredCase]:
        stmt = select(CaseRow).order_by(CaseRow.created_at.desc()).limit(limit)
        async with self._session() as session:
            rows = (await session.execute(stmt)).scalars().all()
        return [row_to_stored_case(row) for row in rows]

    async def delete(self, case_id: str) -> None:
        async with self._transaction() as session:
            row = await session.get(CaseRow, case_id)
            if row is None:
                raise NotFoundError("case", case_id)
            await session.delete(row)
