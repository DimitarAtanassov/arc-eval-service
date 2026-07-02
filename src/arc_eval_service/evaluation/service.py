"""Evaluation orchestration: score one interaction and persist the outcome.

The service is the whole job of ``POST /v1/evaluate``:

1. pick the metrics for the request's ``task_type``;
2. score them concurrently via the judge engine (best-effort per metric);
3. persist the interaction and every result (including failures) for
   data-level observability;
4. return only the metrics that scored successfully.

Scoring never raises: the judge engine degrades a failed metric to an errored
result, so one bad metric (or a missing judge model) cannot fail the request.
Persistence is best-effort too -- if the observability write fails it is logged,
not surfaced, so the caller still gets its scores.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import uuid4

from arc_eval_service.db.repositories import (
    EvalRequestRepository,
    EvaluationResultRepository,
)
from arc_eval_service.evaluation.contract import (
    EvaluateRequest,
    EvaluateResponse,
    MetricResult,
)
from arc_eval_service.evaluation.records import NewEvalRequest, NewEvaluationResult
from arc_eval_service.evaluation.schemas import EvaluationCase, EvaluationResult
from arc_eval_service.judging.engine import JudgeEngine
from arc_eval_service.prompts.schema import PromptLibrary

logger = logging.getLogger("arc_eval_service.evaluation.service")

# Which metrics run for a given task type. Unknown task types fall back to
# ``DEFAULT_METRICS``. This is a small in-code table on purpose: it is a scoring
# policy, not configuration, and lives next to the code that applies it.
TASK_METRICS: dict[str, tuple[str, ...]] = {
    "summarization": ("faithfulness", "answer_relevance"),
}
DEFAULT_METRICS: tuple[str, ...] = ("answer_relevance", "safety")


class EvaluationService:
    """Scores one interaction across its task's metrics and stores the outcome."""

    def __init__(
        self,
        *,
        engine: JudgeEngine,
        library: PromptLibrary,
        requests: EvalRequestRepository,
        results: EvaluationResultRepository,
    ) -> None:
        self._engine = engine
        self._library = library
        self._requests = requests
        self._results = results

    async def evaluate(self, request: EvaluateRequest) -> EvaluateResponse:
        """Score the interaction, persist it, and return the successful metrics."""
        request_id = str(uuid4())
        metric_names = self._metrics_for(request.task_type)
        case = _build_case(request, request_id=request_id)

        scored = await asyncio.gather(
            *(
                self._engine.score(name, case, case_id=request_id)
                for name in metric_names
            )
        )

        await self._persist(request_id, request, case, scored)
        return EvaluateResponse(results=[self._to_metric_result(r) for r in scored if r.error is None])

    def _metrics_for(self, task_type: str) -> tuple[str, ...]:
        metrics = TASK_METRICS.get(task_type)
        if metrics is None:
            logger.warning(
                "unknown task type; using default metrics",
                extra={"task_type": task_type, "metrics": DEFAULT_METRICS},
            )
            return DEFAULT_METRICS
        return metrics

    def _version(self, metric_name: str) -> str | None:
        """The evaluator (rubric) version for a metric, if it is defined."""
        if metric_name not in self._library.metrics:
            return None
        return self._library.metrics[metric_name].version

    def _to_metric_result(self, result: EvaluationResult) -> MetricResult:
        # The metric is the evaluator: its name and rubric version identify what
        # produced the score.
        return MetricResult(
            metric_name=result.metric,
            score=result.score,
            reasoning=result.explanation,
            evaluator_name=result.metric,
            evaluator_version=self._version(result.metric),
        )

    async def _persist(
        self,
        request_id: str,
        request: EvaluateRequest,
        case: EvaluationCase,
        scored: list[EvaluationResult],
    ) -> None:
        """Store the interaction and every result. Best-effort: log and swallow."""
        metadata = request.metadata
        variables = _variables(case)
        new_request = NewEvalRequest(
            id=request_id,
            task_type=request.task_type,
            input_text=request.input_text,
            output_text=request.output_text,
            prompt=request.prompt,
            inference_id=metadata.inference_id,
            model_id=metadata.model_id,
            request_metadata=metadata.model_dump(),
        )
        new_results = [
            NewEvaluationResult(
                id=str(uuid4()),
                eval_request_id=request_id,
                inference_id=metadata.inference_id,
                model_id=metadata.model_id,
                metric_name=result.metric,
                score=result.score,
                passed=result.passed,
                reasoning=result.explanation,
                evaluator_name=result.metric,
                evaluator_version=self._version(result.metric),
                judge=_judge_json(result),
                prompt=_prompt_json(result, variables),
                latency_ms=result.latency_ms,
                error=result.error,
            )
            for result in scored
        ]
        try:
            await self._requests.create(new_request)
            await self._results.create_many(new_results)
        except Exception:  # noqa: BLE001 - observability write must not fail the request
            logger.exception(
                "failed to persist evaluation",
                extra={"eval_request_id": request_id},
            )


def _build_case(request: EvaluateRequest, *, request_id: str) -> EvaluationCase:
    """Map the wire request onto the judging engine's case.

    ``input_text`` is also passed as the grounding ``context`` so grounded metrics
    (faithfulness) can check the output against the source without a separate
    field. Metrics that do not need context ignore it.
    """
    return EvaluationCase(
        request_id=request_id,
        input=request.input_text,
        output=request.output_text,
        context=[request.input_text],
        metadata={"task_type": request.task_type},
    )


def _variables(case: EvaluationCase) -> dict[str, Any]:
    """The input variables the metric prompt was rendered with."""
    return {
        "input": case.input,
        "output": case.output,
        "context": case.context,
        "reference": case.reference,
    }


def _judge_json(result: EvaluationResult) -> dict[str, Any] | None:
    """The judge, the model it resolved to, its settings, and the system prompt."""
    if result.model is None:
        return None
    return {
        "name": result.judge_name,
        "version": result.judge_version,
        "model": result.model,
        "provider": result.provider,
        "temperature": result.temperature,
        "max_tokens": result.max_tokens,
        "system_prompt": result.system_prompt,
    }


def _prompt_json(result: EvaluationResult, variables: dict[str, Any]) -> dict[str, Any]:
    """The metric prompt template and the input variables it was rendered with."""
    return {"template": result.prompt_template, "variables": variables}
