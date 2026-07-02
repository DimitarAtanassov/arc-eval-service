"""The judge engine: score a metric against a case with a judge model.

Given a metric name and a case it resolves the metric criterion and the judge from
the prompt library, composes the system prompt (optional judge persona, then the
metric rubric), renders the case into the user prompt, runs the judge model asking
for a structured :class:`Verdict`, parses that verdict, and applies the metric's
threshold. A validation, model or parse failure degrades that metric into an
errored result and is never raised, so one bad metric cannot fail the whole
request.
"""

from __future__ import annotations

import logging
from time import perf_counter

from arc_eval_service.catalog import Catalog
from arc_eval_service.catalog.judge import JudgeDefinition
from arc_eval_service.catalog.metric import MetricDefinition, render_case
from arc_eval_service.domain.errors import (
    EvaluationError,
    ModelError,
    UnknownJudgeError,
    UnknownMetricError,
    UnknownModelError,
)
from arc_eval_service.domain.evaluation import EvaluationCase, MetricScore
from arc_eval_service.judging.ports import JudgeModel, ModelCompletion, ModelSettings
from arc_eval_service.judging.profiles import ModelRegistry
from arc_eval_service.judging.verdict import Verdict, parse_verdict

logger = logging.getLogger("arc_eval_service.judging.engine")


class JudgeEngine:
    """Scores one metric against one case with a resolved judge (best-effort)."""

    def __init__(
        self, *, library: Catalog, models: ModelRegistry, default_judge: str
    ) -> None:
        self._library = library
        self._models = models
        self._default_judge = default_judge

    async def score(
        self,
        metric: str,
        case: EvaluationCase,
        *,
        case_id: str,
        judge: str | None = None,
    ) -> MetricScore:
        """Score one metric: compose -> render -> model -> parse, capturing errors."""
        start = perf_counter()
        judge_name = judge or self._default_judge
        try:
            metric_def = self._library.metric(metric)
            _check_requires(metric, metric_def, case)
            judge_def = self._library.judge(judge_name)
            model = self._models.resolve(judge_def.model_profile)
            settings = ModelSettings(
                temperature=judge_def.temperature, max_tokens=judge_def.max_tokens
            )
            system = _compose_system(judge_def, metric_def.rubric)
            user = render_case(metric_def.template, case)
            completion = await self._complete(model, system, user, settings)
            verdict = parse_verdict(completion.text)
        except (
            EvaluationError,
            ModelError,
            UnknownMetricError,
            UnknownJudgeError,
            UnknownModelError,
        ) as exc:
            return _errored(metric, start, exc, level=logging.WARNING)
        except Exception as exc:  # noqa: BLE001 - isolate a buggy metric from peers
            return _errored(metric, start, exc, level=logging.ERROR)

        latency_ms = round((perf_counter() - start) * 1000, 4)
        return MetricScore(
            metric=metric,
            model=completion.model,
            provider=model.provider,
            judge_name=judge_name,
            judge_version=judge_def.version,
            prompt_template=metric_def.template,
            system_prompt=system,
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
            score=verdict.score,
            passed=verdict.score >= metric_def.threshold,
            label=verdict.label,
            explanation=verdict.explanation,
            latency_ms=latency_ms,
        )

    async def _complete(
        self, model: JudgeModel, system: str, user: str, settings: ModelSettings
    ) -> ModelCompletion:
        """Call the judge model for a single-turn, structured completion."""
        return await model.complete(
            system=system, prompt=user, settings=settings, response_schema=Verdict
        )


def _compose_system(judge: JudgeDefinition, rubric: str) -> str:
    """Compose the system prompt: optional judge persona, then the metric rubric.

    The output shape is not described here: the engine requests a structured
    :class:`Verdict` from the model, so the JSON contract lives in that schema.
    """
    layers: list[str] = []
    if judge.system_prompt:
        layers.append(judge.system_prompt.strip())
    layers.append(rubric.strip())
    return "\n\n".join(layers)


def _check_requires(name: str, metric: MetricDefinition, case: EvaluationCase) -> None:
    for field in metric.requires:
        value = getattr(case, field, None)
        if value is None or (isinstance(value, str | list) and len(value) == 0):
            raise EvaluationError(f"metric '{name}' requires '{field}'")


def _errored(metric: str, start: float, exc: Exception, *, level: int) -> MetricScore:
    latency_ms = round((perf_counter() - start) * 1000, 4)
    logger.log(level, "metric failed", extra={"metric": metric, "error": str(exc)})
    return MetricScore(
        metric=metric,
        score=0.0,
        passed=False,
        latency_ms=latency_ms,
        error=str(exc),
    )
