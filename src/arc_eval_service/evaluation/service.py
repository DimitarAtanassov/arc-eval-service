"""Evaluation orchestration: the lifecycle of an evaluation request.

The service owns orchestration only: validate the request, persist the case, run
each metric through the :class:`~arc_eval_service.judging.engine.JudgeEngine`, and
persist the per-metric results. There is no aggregate. Metric execution, the
model call and per-metric error handling live in the engine; discovery lives in
:class:`~arc_eval_service.discovery.service.DiscoveryService`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from arc_telemetry import get_tracer

from arc_eval_service.core.errors import (
    EvaluationError,
    UnknownMetricError,
    UnknownModelError,
)
from arc_eval_service.db.repositories import CaseRepository, ResultRepository
from arc_eval_service.evaluation.schemas import (
    EvaluationCase,
    EvaluationRequest,
    EvaluationResponse,
    EvaluationResult,
    MetricSpec,
    StoredCase,
)
from arc_eval_service.judging.engine import JudgeEngine
from arc_eval_service.judging.profiles import ModelRegistry
from arc_eval_service.metrics.registry import MetricRegistry

ROOT_SPAN_NAME = "arc.eval.evaluate"


class EvaluationService:
    """Orchestrates metric scoring across the requested metrics."""

    def __init__(
        self,
        *,
        cases: CaseRepository,
        results: ResultRepository,
        metrics: MetricRegistry,
        models: ModelRegistry,
    ) -> None:
        self._cases = cases
        self._results = results
        self._metrics = metrics
        self._models = models
        self._engine = JudgeEngine(metrics=metrics, models=models)

    async def evaluate(
        self, request: EvaluationRequest, *, trace_id: str | None = None
    ) -> EvaluationResponse:
        """Score a case against its metrics, persisting the case and results."""
        self._validate(request.metrics)
        stored = self._new_case(request.case, trace_id)
        await self._cases.create(stored)
        results = await self._run(stored, request.metrics)
        return EvaluationResponse.of(stored, results)

    async def batch(
        self, requests: list[EvaluationRequest]
    ) -> list[EvaluationResponse]:
        """Evaluate many requests in order."""
        return [await self.evaluate(request) for request in requests]

    async def rerun(
        self, case_id: str, override: list[MetricSpec] | None = None
    ) -> EvaluationResponse:
        """Re-score a stored case, replacing its results.

        Without ``override`` the metrics are taken from the prior results (the
        config of those metrics is not retained, so re-running the custom metric
        needs explicit metrics).
        """
        stored = await self._cases.get(case_id)
        specs = override or await self._specs_from_results(case_id)
        if not specs:
            raise EvaluationError("cannot rerun: no metrics available")
        self._validate(specs)
        results = await self._run(stored, specs)
        return EvaluationResponse.of(stored, results)

    async def get(self, case_id: str) -> EvaluationResponse:
        """Return a stored case with its results or raise ``NotFoundError``."""
        stored = await self._cases.get(case_id)
        results = await self._results.get_for_case(case_id)
        return EvaluationResponse.of(stored, results)

    async def recent(self, limit: int) -> list[EvaluationResponse]:
        """Return up to ``limit`` cases with their results, most recent first."""
        cases = await self._cases.list_recent(limit)
        grouped = await self._results.get_for_cases([c.case_id for c in cases])
        return [EvaluationResponse.of(c, grouped[c.case_id]) for c in cases]

    async def delete(self, case_id: str) -> None:
        """Delete a stored case and its results, or raise ``NotFoundError``."""
        await self._cases.delete(case_id)

    def _validate(self, specs: list[MetricSpec]) -> None:
        """Reject unknown metrics/models before any model work or persistence."""
        for spec in specs:
            if not self._metrics.has(spec.metric):
                raise UnknownMetricError(spec.metric)
            if not self._models.has(spec.model):
                raise UnknownModelError(spec.model or "<default>")

    def _new_case(self, case: EvaluationCase, trace_id: str | None) -> StoredCase:
        return StoredCase(
            case_id=str(uuid4()),
            trace_id=trace_id,
            created_at=datetime.now(UTC),
            case=case,
        )

    async def _run(
        self, stored: StoredCase, specs: list[MetricSpec]
    ) -> list[EvaluationResult]:
        tracer = get_tracer(__name__)
        with tracer.start_as_current_span(ROOT_SPAN_NAME) as root:
            root.set_attribute("case_id", stored.case_id)
            root.set_attribute("request_id", stored.case.request_id)
            root.set_attribute("metric_count", len(specs))
            results = [
                await self._engine.score(spec, stored.case, case_id=stored.case_id)
                for spec in specs
            ]
        await self._results.set_for_case(stored.case_id, results)
        return results

    async def _specs_from_results(self, case_id: str) -> list[MetricSpec]:
        seen: set[tuple[str, str | None]] = set()
        specs: list[MetricSpec] = []
        for result in await self._results.get_for_case(case_id):
            key = (result.metric, result.model)
            if key in seen:
                continue
            seen.add(key)
            specs.append(MetricSpec(metric=result.metric, model=result.model))
        return specs
