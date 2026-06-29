"""Evaluation orchestration. ALL evaluation control-flow lives here.

Responsibilities: validate the request, create/persist the record, drive the
registered evaluators (each within its own span), aggregate the outcome and
persist the result. The api/ layer stays free of this logic; evaluators stay
free of persistence and tracing.

Both execution modes are supported:

* sync  -> :meth:`evaluate` runs inline and returns the completed record.
* async -> :meth:`submit` persists a PENDING record and returns immediately;
  :meth:`run_async` (scheduled as a background task) executes it later and the
  caller polls :meth:`get`.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from statistics import fmean
from time import perf_counter
from uuid import uuid4

from opentelemetry.trace import Span, Tracer

from arc_eval_service.core.errors import EvaluationError, UnknownEvaluatorError
from arc_eval_service.evaluators.registry import EvaluatorRegistry
from arc_eval_service.observability.tracing import get_tracer
from arc_eval_service.schemas.models import (
    EvaluationRecord,
    EvaluationRequest,
    EvaluationResult,
    EvaluationStatus,
    EvaluatorInfo,
    EvaluatorInput,
    EvaluatorSpec,
    ExecutionMode,
)
from arc_eval_service.storage.base import EvaluationStore

ROOT_SPAN_NAME = "arc.eval.evaluate"
EVALUATOR_SPAN_NAME = "arc.eval.evaluator"

logger = logging.getLogger("arc_eval_service.services.evaluation")


class EvaluationService:
    """Orchestrates evaluation requests across the registered evaluators."""

    def __init__(self, *, store: EvaluationStore, registry: EvaluatorRegistry) -> None:
        self._store = store
        self._registry = registry

    # -- public orchestration API -----------------------------------------

    async def evaluate(self, request: EvaluationRequest) -> EvaluationRecord:
        """Run a request synchronously and return the completed record."""
        self._validate(request)
        record = self._new_record(request, ExecutionMode.SYNC, EvaluationStatus.RUNNING)
        await self._store.create(record)
        completed = self._execute(record, request)
        await self._store.update(completed)
        return completed

    async def submit(self, request: EvaluationRequest) -> EvaluationRecord:
        """Persist a PENDING record for async execution and return it.

        The caller is responsible for scheduling :meth:`run_async`.
        """
        self._validate(request)
        record = self._new_record(
            request, ExecutionMode.ASYNC, EvaluationStatus.PENDING
        )
        await self._store.create(record)
        return record

    async def run_async(self, evaluation_id: str, request: EvaluationRequest) -> None:
        """Execute a previously submitted request and persist the result.

        Runs as a fire-and-forget background task, so it must never leave the
        record stranded in PENDING: any unexpected failure is logged and the
        record is marked FAILED instead of bubbling up unobserved.
        """
        record = await self._store.get(evaluation_id)
        try:
            completed = self._execute(record, request)
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

    async def get(self, evaluation_id: str) -> EvaluationRecord:
        """Return a stored record or raise ``NotFoundError``."""
        return await self._store.get(evaluation_id)

    async def recent(self, limit: int) -> list[EvaluationRecord]:
        """Return up to ``limit`` records, most recently created first."""
        return await self._store.list_recent(limit)

    def evaluators(self) -> list[EvaluatorInfo]:
        """Return discovery metadata for every registered evaluator."""
        return [
            EvaluatorInfo(name=e.name, description=e.description)
            for e in self._registry.available()
        ]

    # -- internals ---------------------------------------------------------

    def _validate(self, request: EvaluationRequest) -> None:
        """Reject requests referencing unknown evaluators before any work."""
        for spec in request.evaluators:
            if not self._registry.has(spec.name):
                raise UnknownEvaluatorError(spec.name)

    def _new_record(
        self,
        request: EvaluationRequest,
        mode: ExecutionMode,
        status: EvaluationStatus,
    ) -> EvaluationRecord:
        return EvaluationRecord(
            evaluation_id=str(uuid4()),
            request_id=request.case.request_id,
            status=status,
            mode=mode,
            created_at=datetime.now(UTC),
        )

    def _execute(
        self, record: EvaluationRecord, request: EvaluationRequest
    ) -> EvaluationRecord:
        """Run all evaluators under a root span and aggregate the outcome."""
        tracer = get_tracer()
        with tracer.start_as_current_span(ROOT_SPAN_NAME) as root:
            root.set_attribute("evaluation_id", record.evaluation_id)
            root.set_attribute("request_id", record.request_id)
            root.set_attribute("evaluator_count", len(request.evaluators))
            results: list[EvaluationResult] = [
                self._run_one(spec, request, record.evaluation_id, tracer)
                for spec in request.evaluators
            ]

        scored = [r for r in results if r.error is None]
        aggregate = round(fmean(r.score for r in scored), 4) if scored else None
        passed = bool(scored) and all(r.passed for r in scored)
        status = EvaluationStatus.COMPLETED if scored else EvaluationStatus.FAILED

        return record.model_copy(
            update={
                "status": status,
                "results": results,
                "aggregate_score": aggregate,
                "passed": passed,
                "completed_at": datetime.now(UTC),
            }
        )

    def _run_one(
        self,
        spec: EvaluatorSpec,
        request: EvaluationRequest,
        evaluation_id: str,
        tracer: Tracer,
    ) -> EvaluationResult:
        """Run a single evaluator within its span, timing and capturing errors."""
        evaluator = self._registry.get(spec.name)
        data = EvaluatorInput(case=request.case, config=spec.config)
        with tracer.start_as_current_span(EVALUATOR_SPAN_NAME) as span:
            span.set_attribute("evaluator_name", spec.name)
            span.set_attribute("evaluation_id", evaluation_id)
            span.set_attribute("request_id", request.case.request_id)
            start = perf_counter()
            try:
                outcome = evaluator.evaluate(data)
            except EvaluationError as exc:
                # Expected failure (missing input/bad config): captured per
                # evaluator, never fatal to the request.
                return self._errored(spec, start, span, exc, level=logging.WARNING)
            except Exception as exc:  # noqa: BLE001 - isolate buggy evaluator from peers
                # Unexpected fault: contain it so one evaluator can't strand the
                # whole record or 500 the request.
                return self._errored(spec, start, span, exc, level=logging.ERROR)
            latency_ms = round((perf_counter() - start) * 1000, 4)
            result = outcome.model_copy(update={"latency_ms": latency_ms})
            span.set_attribute("latency_ms", result.latency_ms)
            span.set_attribute("score", result.score)
            return result

    def _errored(
        self,
        spec: EvaluatorSpec,
        start: float,
        span: Span,
        exc: Exception,
        *,
        level: int,
    ) -> EvaluationResult:
        """Build an errored result, recording latency and the fault on the span."""
        latency_ms = round((perf_counter() - start) * 1000, 4)
        span.set_attribute("latency_ms", latency_ms)
        span.set_attribute("error", str(exc))
        logger.log(level, "evaluator failed", extra={"evaluator_name": spec.name})
        return EvaluationResult(
            evaluator_name=spec.name,
            score=0.0,
            passed=False,
            latency_ms=latency_ms,
            error=str(exc),
        )
