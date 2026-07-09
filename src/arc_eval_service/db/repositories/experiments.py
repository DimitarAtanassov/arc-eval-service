from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from arc_eval_service.db.models import (
    EvaluationResultRow,
    ExperimentRow,
    ExperimentRunRow,
)
from arc_eval_service.db.records import (
    NewExperiment,
    NewExperimentRun,
    StoredExperiment,
    StoredExperimentRun,
)
from arc_eval_service.db.repositories.base import BaseRepository
from arc_eval_service.domain.errors import ExperimentNameConflictError
from arc_eval_service.domain.experiment import ExperimentMetricAggregate

_NAME_CONSTRAINT = "uq_experiments_name"


def _violates_constraint(exc: IntegrityError, name: str) -> bool:
    """True when the IntegrityError is a violation of the named DB constraint.

    Reads the structured constraint name the driver reports (psycopg exposes it as
    ``orig.diag.constraint_name``, asyncpg as ``orig.constraint_name``) instead of
    substring-matching the driver's message text, which is locale- and
    format-dependent. Returns False when no constraint name is available, so an
    unclassifiable error is re-raised rather than mislabeled a name conflict.
    """
    orig = exc.orig
    diag = getattr(orig, "diag", None)
    constraint: object = getattr(diag, "constraint_name", None) or getattr(
        orig, "constraint_name", None
    )
    return constraint == name


def new_experiment_to_row(item: NewExperiment) -> ExperimentRow:
    """Map a new experiment record to its ORM row."""
    return ExperimentRow(
        id=item.id,
        name=item.name,
        model_name=item.model_name,
        generation_config=item.generation_config,
        prompt_template=item.prompt_template,
        variables=item.variables,
        description=item.description,
        created_at=item.created_at,
    )


def row_to_stored_experiment(row: ExperimentRow) -> StoredExperiment:
    """Map a persisted experiment row back to a storage record."""
    return StoredExperiment(
        id=row.id,
        name=row.name,
        model_name=row.model_name,
        generation_config=row.generation_config,
        prompt_template=row.prompt_template,
        variables=row.variables,
        description=row.description,
        created_at=row.created_at,
    )


def new_experiment_run_to_row(item: NewExperimentRun) -> ExperimentRunRow:
    """Map a new experiment run record to its ORM row."""
    return ExperimentRunRow(
        id=item.id,
        experiment_id=item.experiment_id,
        inference_id=item.inference_id,
        eval_request_id=item.eval_request_id,
        created_at=item.created_at,
    )


class ExperimentRepository(BaseRepository):
    """Persistence for experiments."""

    async def create(
        self, item: NewExperiment, *, session: AsyncSession | None = None
    ) -> StoredExperiment:
        """Insert an experiment, raising ExperimentNameConflictError on a duplicate name."""
        async with self._write(session) as active:
            active.add(new_experiment_to_row(item))
            try:
                await active.flush()
            except IntegrityError as exc:
                if _violates_constraint(exc, _NAME_CONSTRAINT):
                    raise ExperimentNameConflictError(item.name) from exc
                raise
        return StoredExperiment(**item.model_dump())

    async def get(self, experiment_id: str) -> StoredExperiment | None:
        """Return one experiment by id, or None when absent."""
        async with self._read() as session:
            row = await session.get(ExperimentRow, experiment_id)
        return row_to_stored_experiment(row) if row is not None else None

    async def get_by_name(self, name: str) -> StoredExperiment | None:
        """Return one experiment by unique name, or None when absent."""
        stmt = select(ExperimentRow).where(ExperimentRow.name == name)
        async with self._read() as session:
            row = (await session.scalars(stmt)).first()
        return row_to_stored_experiment(row) if row is not None else None

    async def list_recent(self, limit: int) -> list[StoredExperiment]:
        """Return the most recent experiments, newest first (bounded page size)."""
        stmt = (
            select(ExperimentRow).order_by(ExperimentRow.created_at.desc()).limit(limit)
        )
        async with self._read() as session:
            rows = (await session.scalars(stmt)).all()
        return [row_to_stored_experiment(row) for row in rows]

    async def aggregate_scores(
        self, experiment_id: str
    ) -> list[ExperimentMetricAggregate]:
        """Average score and count per metric for an experiment's evaluated inferences.

        Joins experiment_runs to evaluation_results on eval_request_id (the precise
        link that avoids double-counting re-evaluations). Filters error IS NULL to
        exclude failed metric scores from the aggregate. Runs without an eval_request_id
        are excluded by the INNER JOIN.
        """
        stmt = (
            select(
                EvaluationResultRow.metric_name,
                func.avg(EvaluationResultRow.score).label("average_score"),
                func.count().label("evaluated_count"),
            )
            .join(
                ExperimentRunRow,
                ExperimentRunRow.eval_request_id == EvaluationResultRow.eval_request_id,
            )
            .where(
                ExperimentRunRow.experiment_id == experiment_id,
                EvaluationResultRow.error.is_(None),
            )
            .group_by(EvaluationResultRow.metric_name)
            .order_by(EvaluationResultRow.metric_name)
        )
        async with self._read() as session:
            rows = (await session.execute(stmt)).all()
        return [
            ExperimentMetricAggregate(
                metric_name=row.metric_name,
                average_score=float(row.average_score),
                evaluated_count=int(row.evaluated_count),
            )
            for row in rows
        ]


class ExperimentRunRepository(BaseRepository):
    """Persistence for experiment runs."""

    async def create(
        self, item: NewExperimentRun, *, session: AsyncSession | None = None
    ) -> StoredExperimentRun:
        """Persist one experiment run, joining a caller's transaction when provided."""
        async with self._write(session) as active:
            active.add(new_experiment_run_to_row(item))
        return StoredExperimentRun(**item.model_dump())
