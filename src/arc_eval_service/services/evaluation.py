"""Evaluation orchestration: the lifecycle of an evaluation request.

The service owns *orchestration only*: validate the request, persist a record,
fan the judges out (each run by :class:`~arc_eval_service.services.judging.JudgeRunner`),
aggregate the outcome (:func:`~arc_eval_service.services.aggregation.aggregate_results`),
and persist the result. Single-judge execution, the model call and per-judge
error handling live in the runner; discovery lives in
:class:`~arc_eval_service.services.discovery.DiscoveryService`.

Entry points all funnel through :meth:`_execute` (DRY):
* sync   -> :meth:`evaluate`
* async  -> :meth:`submit` + :meth:`run_async`
* batch  -> :meth:`batch`
* rerun  -> :meth:`rerun` (re-judge a stored case, optionally with new specs)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import uuid4

from arc_telemetry import get_tracer

from arc_eval_service.core.errors import (
    EvaluationError,
    UnknownJudgeError,
    UnknownModelError,
)
from arc_eval_service.judges.registry import JudgeRegistry
from arc_eval_service.models.profiles import ModelRegistry
from arc_eval_service.schemas.models import (
    EvaluationRecord,
    EvaluationRequest,
    EvaluationResult,
    EvaluationStatus,
    ExecutionMode,
    JudgeSpec,
)
from arc_eval_service.services.aggregation import aggregate_results
from arc_eval_service.services.judging import JudgeRunner
from arc_eval_service.storage.evaluation import EvaluationStore

ROOT_SPAN_NAME = "arc.eval.evaluate"

logger = logging.getLogger("arc_eval_service.services.evaluation")


class EvaluationService:
    """Orchestrates LLM-as-a-judge evaluation across the requested judges."""

    def __init__(
        self,
        *,
        store: EvaluationStore,
        judges: JudgeRegistry,
        models: ModelRegistry,
    ) -> None:
        self._store = store
        self._judges = judges
        self._models = models
        self._runner = JudgeRunner(judges=judges, models=models)

    # -- public orchestration API -----------------------------------------

    async def evaluate(self, request: EvaluationRequest) -> EvaluationRecord:
        """Run a request synchronously and return the completed record."""
        self._validate(request)
        record = self._new_record(request, ExecutionMode.SYNC, EvaluationStatus.RUNNING)
        await self._store.create(record)
        completed = await self._execute(record, request)
        await self._store.update(completed)
        return completed

    async def submit(self, request: EvaluationRequest) -> EvaluationRecord:
        """Persist a PENDING record for async execution and return it."""
        self._validate(request)
        record = self._new_record(
            request, ExecutionMode.ASYNC, EvaluationStatus.PENDING
        )
        await self._store.create(record)
        return record

    async def run_async(self, evaluation_id: str, request: EvaluationRequest) -> None:
        """Execute a previously submitted request and persist the result.

        Fire-and-forget: any unexpected failure is logged and the record is
        marked FAILED rather than left stranded in PENDING.
        """
        record = await self._store.get(evaluation_id)
        try:
            completed = await self._execute(record, request)
        except Exception:
            logger.exception(
                "async evaluation crashed",
                extra={"evaluation_id": evaluation_id, "request_id": record.request_id},
            )
            completed = record.model_copy(
                update={
                    "status": EvaluationStatus.FAILED,
                    "completed_at": datetime.now(UTC),
                }
            )
        await self._store.update(completed)

    async def batch(self, requests: list[EvaluationRequest]) -> list[EvaluationRecord]:
        """Evaluate many requests synchronously, preserving input order."""
        return [await self.evaluate(request) for request in requests]

    async def rerun(
        self, evaluation_id: str, override: list[JudgeSpec] | None = None
    ) -> EvaluationRecord:
        """Re-judge a stored case, optionally with different judges/models.

        Persists a NEW record linked to the parent via ``rerun_of``.
        """
        parent = await self._store.get(evaluation_id)
        if parent.case is None:
            raise EvaluationError("cannot rerun: original case was not stored")
        specs = override or parent.specs
        if not specs:
            raise EvaluationError("cannot rerun: no judge specs available")
        request = EvaluationRequest(case=parent.case, judges=specs)
        self._validate(request)
        record = self._new_record(
            request,
            ExecutionMode.SYNC,
            EvaluationStatus.RUNNING,
            rerun_of=evaluation_id,
        )
        await self._store.create(record)
        completed = await self._execute(record, request)
        await self._store.update(completed)
        return completed

    async def get(self, evaluation_id: str) -> EvaluationRecord:
        """Return a stored record or raise ``NotFoundError``."""
        return await self._store.get(evaluation_id)

    async def recent(self, limit: int) -> list[EvaluationRecord]:
        """Return up to ``limit`` records, most recently created first."""
        return await self._store.list_recent(limit)

    async def delete(self, evaluation_id: str) -> None:
        """Delete a stored record or raise ``NotFoundError`` if it is absent."""
        await self._store.delete(evaluation_id)

    # -- internals ---------------------------------------------------------

    def _validate(self, request: EvaluationRequest) -> None:
        """Reject structurally invalid requests before any model work.

        Per-case field requirements are enforced per-judge (and degrade) so a
        single under-specified judge does not fail the whole request.
        """
        for spec in request.judges:
            if not self._judges.has(spec.judge):
                raise UnknownJudgeError(spec.judge)
            if not self._models.has(spec.model):
                raise UnknownModelError(spec.model or "<default>")

    def _new_record(
        self,
        request: EvaluationRequest,
        mode: ExecutionMode,
        status: EvaluationStatus,
        *,
        rerun_of: str | None = None,
    ) -> EvaluationRecord:
        return EvaluationRecord(
            evaluation_id=str(uuid4()),
            request_id=request.case.request_id,
            status=status,
            mode=mode,
            created_at=datetime.now(UTC),
            case=request.case,
            specs=request.judges,
            rerun_of=rerun_of,
        )

    async def _execute(
        self, record: EvaluationRecord, request: EvaluationRequest
    ) -> EvaluationRecord:
        """Run all judges under a root span and aggregate the outcome."""
        tracer = get_tracer(__name__)
        with tracer.start_as_current_span(ROOT_SPAN_NAME) as root:
            root.set_attribute("evaluation_id", record.evaluation_id)
            root.set_attribute("request_id", record.request_id)
            root.set_attribute("judge_count", len(request.judges))
            results: list[EvaluationResult] = [
                await self._runner.run_one(spec, request.case, record.evaluation_id)
                for spec in request.judges
            ]
        outcome = aggregate_results(results)
        return record.model_copy(
            update={
                "status": outcome.status,
                "results": results,
                "aggregate_score": outcome.aggregate_score,
                "passed": outcome.passed,
                "completed_at": datetime.now(UTC),
            }
        )
