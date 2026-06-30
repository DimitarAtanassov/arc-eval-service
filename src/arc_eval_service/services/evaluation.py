"""Evaluation orchestration. ALL evaluation control-flow lives here.

The service runs **LLM-as-a-judge only**. For each requested judge it resolves a
judge strategy (pure) and a model adapter (the configured profile), builds the
prompt, calls the model (the imperative shell), parses the verdict and records
the result. Judges run independently: a model/parse/validation failure degrades
that judge into an errored result and never fails the whole request.

Entry points all funnel through :meth:`_execute` (DRY):
* sync   -> :meth:`evaluate`
* async  -> :meth:`submit` + :meth:`run_async`
* batch  -> :meth:`batch`
* rerun  -> :meth:`rerun` (re-judge a stored case, optionally with new specs)
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from statistics import fmean
from time import perf_counter
from uuid import uuid4

from arc_telemetry import (
    LLMInvocation,
    Message,
    Role,
    evaluation_span,
    get_tracer,
    llm_span,
)

from arc_eval_service.core.errors import (
    EvaluationError,
    ModelError,
    UnknownJudgeError,
    UnknownModelError,
)
from arc_eval_service.judges.base import Judge, JudgePrompt
from arc_eval_service.judges.registry import JudgeRegistry
from arc_eval_service.models.base import JudgeModel, ModelCompletion, ModelSettings
from arc_eval_service.models.profiles import ModelRegistry
from arc_eval_service.schemas.models import (
    ConfigValue,
    EvaluationCase,
    EvaluationRecord,
    EvaluationRequest,
    EvaluationResult,
    EvaluationStatus,
    ExecutionMode,
    JudgeInfo,
    JudgeSpec,
    ModelProfileInfo,
)
from arc_eval_service.storage.base import EvaluationStore

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

    def judges(self) -> list[JudgeInfo]:
        """Return discovery metadata for every registered judge."""
        return [
            JudgeInfo(name=j.name, description=j.description, requires=list(j.requires))
            for j in self._judges.available()
        ]

    def model_profiles(self) -> list[ModelProfileInfo]:
        """Return discovery metadata for every configured model profile."""
        return self._models.list_profiles()

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
                await self._run_one(spec, request.case, record.evaluation_id)
                for spec in request.judges
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

    async def _run_one(
        self, spec: JudgeSpec, case: EvaluationCase, evaluation_id: str
    ) -> EvaluationResult:
        """Run a single judge: build prompt -> model -> parse, capturing errors."""
        start = perf_counter()
        try:
            judge = self._judges.get(spec.judge)
            self._check_requires(judge, case)
            model = self._models.resolve(spec.model, model_override=spec.model_override)
            prompt = judge.build_prompt(case, spec.config)
            with evaluation_span(spec.judge) as ev:
                ev.span.set_attribute("evaluation_id", evaluation_id)
                ev.span.set_attribute("request_id", case.request_id)
                completion = await self._complete(model, prompt)
                verdict = judge.parse(completion.text)
                ev.set_result(
                    score=verdict.score,
                    label=verdict.label,
                    explanation=verdict.explanation,
                )
        except (EvaluationError, ModelError, UnknownModelError) as exc:
            return self._errored(spec, start, exc, level=logging.WARNING)
        except Exception as exc:  # noqa: BLE001 - isolate a buggy judge from peers
            return self._errored(spec, start, exc, level=logging.ERROR)

        threshold = _threshold(spec.config, judge)
        latency_ms = round((perf_counter() - start) * 1000, 4)
        return EvaluationResult(
            judge=spec.judge,
            model=completion.model,
            score=verdict.score,
            passed=verdict.score >= threshold,
            label=verdict.label,
            explanation=verdict.explanation,
            latency_ms=latency_ms,
        )

    async def _complete(
        self, model: JudgeModel, prompt: JudgePrompt
    ) -> ModelCompletion:
        """Call the judge model inside an ``llm.call`` span (arc.llm.*).

        The rendered system + user judge prompt and the model's verdict are
        captured as message/choice events (content-gated) so the full judge
        interaction is visible on the trace.
        """
        messages = [Message(role=Role.USER, content=prompt.user)]
        if prompt.system:
            messages.insert(0, Message(role=Role.SYSTEM, content=prompt.system))
        invocation = LLMInvocation(
            provider=model.provider,
            request_model=model.name,
            messages=tuple(messages),
        )
        with llm_span(invocation) as rec:
            completion = await model.complete(
                system=prompt.system, prompt=prompt.user, settings=ModelSettings()
            )
            rec.set_response(
                response_model=completion.model,
                input_tokens=completion.input_tokens,
                output_tokens=completion.output_tokens,
                completion=completion.text,
            )
            return completion

    @staticmethod
    def _check_requires(judge: Judge, case: EvaluationCase) -> None:
        for field in judge.requires:
            value = getattr(case, field, None)
            if value is None or (isinstance(value, str | list) and len(value) == 0):
                raise EvaluationError(f"judge '{judge.name}' requires '{field}'")

    def _errored(
        self, spec: JudgeSpec, start: float, exc: Exception, *, level: int
    ) -> EvaluationResult:
        latency_ms = round((perf_counter() - start) * 1000, 4)
        logger.log(
            level, "judge failed", extra={"judge": spec.judge, "error": str(exc)}
        )
        return EvaluationResult(
            judge=spec.judge,
            score=0.0,
            passed=False,
            latency_ms=latency_ms,
            error=str(exc),
        )


def _threshold(config: Mapping[str, ConfigValue], judge: Judge) -> float:
    """Resolve the pass threshold: config override or the judge default."""
    raw = config.get("pass_threshold")
    if isinstance(raw, int | float) and not isinstance(raw, bool):
        return float(raw)
    return judge.default_threshold
