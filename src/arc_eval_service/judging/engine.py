"""The judge engine: score a metric against a case on a model.

Given a :class:`MetricSpec` and a case it resolves the metric and model, renders
the metric's rubric into a strict-JSON prompt, runs the model, parses the verdict
and applies the metric's threshold. A validation, model or parse failure degrades
that metric into an errored result and is never raised, so one bad metric cannot
fail the whole request.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from time import perf_counter

from arc_eval_service.core.errors import (
    EvaluationError,
    ModelError,
    UnknownModelError,
)
from arc_eval_service.evaluation.schemas import (
    ConfigValue,
    EvaluationCase,
    EvaluationResult,
    MetricSpec,
)
from arc_eval_service.judging.model import JudgeModel, ModelCompletion, ModelSettings
from arc_eval_service.judging.profiles import ModelRegistry
from arc_eval_service.judging.verdict import VERDICT_INSTRUCTION, parse_verdict
from arc_eval_service.metrics.base import Metric
from arc_eval_service.metrics.registry import MetricRegistry

logger = logging.getLogger("arc_eval_service.judging.engine")


class JudgeEngine:
    """Scores one metric against one case on a resolved model (best-effort)."""

    def __init__(self, *, metrics: MetricRegistry, models: ModelRegistry) -> None:
        self._metrics = metrics
        self._models = models

    async def score(
        self, spec: MetricSpec, case: EvaluationCase, *, case_id: str
    ) -> EvaluationResult:
        """Score a single metric: render -> model -> parse, capturing errors."""
        start = perf_counter()
        try:
            metric = self._metrics.get(spec.metric)
            _check_requires(metric, case)
            model = self._models.resolve(spec.model, model_override=spec.model_override)
            system = f"{metric.instructions(spec.config)}\n\n{VERDICT_INSTRUCTION}"
            user = metric.render(case)
            completion = await self._complete(model, system, user)
            verdict = parse_verdict(completion.text)
        except (EvaluationError, ModelError, UnknownModelError) as exc:
            return _errored(spec, start, exc, level=logging.WARNING)
        except Exception as exc:  # noqa: BLE001 - isolate a buggy metric from peers
            return _errored(spec, start, exc, level=logging.ERROR)

        threshold = _resolve_threshold(spec.config, metric)
        latency_ms = round((perf_counter() - start) * 1000, 4)
        return EvaluationResult(
            metric=spec.metric,
            model=completion.model,
            score=verdict.score,
            passed=verdict.score >= threshold,
            label=verdict.label,
            explanation=verdict.explanation,
            latency_ms=latency_ms,
        )

    async def _complete(
        self, model: JudgeModel, system: str, user: str
    ) -> ModelCompletion:
        """Call the judge model for a single-turn completion."""
        return await model.complete(
            system=system, prompt=user, settings=ModelSettings()
        )


def _check_requires(metric: Metric, case: EvaluationCase) -> None:
    for field in metric.requires:
        value = getattr(case, field, None)
        if value is None or (isinstance(value, str | list) and len(value) == 0):
            raise EvaluationError(f"metric '{metric.name}' requires '{field}'")


def _errored(
    spec: MetricSpec, start: float, exc: Exception, *, level: int
) -> EvaluationResult:
    latency_ms = round((perf_counter() - start) * 1000, 4)
    logger.log(level, "metric failed", extra={"metric": spec.metric, "error": str(exc)})
    return EvaluationResult(
        metric=spec.metric,
        score=0.0,
        passed=False,
        latency_ms=latency_ms,
        error=str(exc),
    )


def _resolve_threshold(config: Mapping[str, ConfigValue], metric: Metric) -> float:
    """Resolve the pass threshold: config override or the metric default."""
    raw = config.get("pass_threshold")
    if isinstance(raw, int | float) and not isinstance(raw, bool):
        return float(raw)
    return metric.threshold
