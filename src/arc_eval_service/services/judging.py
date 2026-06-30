"""Single-judge execution (imperative shell): prompt -> model -> verdict.

The orchestrator hands one ``(spec, case)`` to :meth:`JudgeRunner.run_one`; the
runner resolves the judge strategy and model adapter, runs the model inside an
``arc.llm.call`` span, parses the verdict and returns a per-judge result. A
validation, model or parse failure degrades that judge into an errored result
and is never raised, so one bad judge cannot fail the whole request.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from time import perf_counter

from arc_telemetry import (
    LLMInvocation,
    Message,
    Role,
    evaluation_span,
    llm_span,
)

from arc_eval_service.core.errors import (
    EvaluationError,
    ModelError,
    UnknownModelError,
)
from arc_eval_service.judges.base import Judge, JudgePrompt
from arc_eval_service.judges.registry import JudgeRegistry
from arc_eval_service.models.base import JudgeModel, ModelCompletion, ModelSettings
from arc_eval_service.models.profiles import ModelRegistry
from arc_eval_service.schemas.models import (
    ConfigValue,
    EvaluationCase,
    EvaluationResult,
    JudgeSpec,
)

logger = logging.getLogger("arc_eval_service.services.judging")


class JudgeRunner:
    """Runs one judge against one case on a resolved model (best-effort)."""

    def __init__(self, *, judges: JudgeRegistry, models: ModelRegistry) -> None:
        self._judges = judges
        self._models = models

    async def run_one(
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

    @staticmethod
    def _errored(
        spec: JudgeSpec, start: float, exc: Exception, *, level: int
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
