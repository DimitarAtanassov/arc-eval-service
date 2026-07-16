"""Pure mappers between the wire contract, the domain, and persistence records.

These translate an :class:`EvaluateRequest` into the judging engine's
:class:`EvaluationCase`, a :class:`MetricScore` into the wire
:class:`MetricResult`, and both into the rows the repositories persist. They are
pure functions and unit-test without a model or a database.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from arc_eval_service.api.schemas import MetricResult
from arc_eval_service.catalog import Catalog
from arc_eval_service.db.records import NewEvalRequest, NewEvaluationResult
from arc_eval_service.domain.evaluation import EvaluationCase, MetricScore
from arc_eval_service.services.interaction import Interaction


def build_case(interaction: Interaction, *, request_id: str) -> EvaluationCase:
    """Map the interaction onto the judging engine's case.

    ``input_text`` is also passed as grounding ``context`` so grounded metrics
    (faithfulness) can check the output against the source without a separate
    field. Metrics that do not need context ignore it.
    """
    return EvaluationCase(
        request_id=request_id,
        input=interaction.input_text,
        output=interaction.output_text,
        context=[interaction.input_text],
    )


def metric_version(library: Catalog, metric_name: str) -> str | None:
    """The evaluator (rubric) version for a metric, if it is defined."""
    if metric_name not in library.metrics:
        return None
    return library.metrics[metric_name].version


def to_metric_result(score: MetricScore, *, library: Catalog) -> MetricResult:
    """Map a domain score to the wire result (the metric is the evaluator)."""
    return MetricResult(
        metric_name=score.metric,
        score=score.score,
        reasoning=score.explanation,
        evaluator_name=score.metric,
        evaluator_version=metric_version(library, score.metric),
    )


def new_eval_request(interaction: Interaction, *, request_id: str) -> NewEvalRequest:
    """Build the request row to persist before scoring.

    The evaluator scores supplied text, so it carries no lab correlation: prompt and
    the inference/model ids are left null and the metadata is empty. Those columns
    are retained for the read surface and slimmed in a later migration.
    """
    return NewEvalRequest(
        id=request_id,
        input_text=interaction.input_text,
        output_text=interaction.output_text,
        prompt=None,
        inference_id=None,
        model_id=None,
        request_metadata={},
    )


def new_eval_results(
    scored: list[MetricScore],
    *,
    request_id: str,
    case: EvaluationCase,
    library: Catalog,
) -> list[NewEvaluationResult]:
    """Build one result row per score (successful or errored)."""
    variables = _variables(case)
    return [
        NewEvaluationResult(
            id=str(uuid4()),
            eval_request_id=request_id,
            inference_id=None,
            model_id=None,
            metric_name=score.metric,
            score=score.score,
            passed=score.passed,
            reasoning=score.explanation,
            evaluator_name=score.metric,
            evaluator_version=metric_version(library, score.metric),
            judge=_judge_json(score),
            prompt=_prompt_json(score, variables),
            latency_ms=score.latency_ms,
            error=score.error,
        )
        for score in scored
    ]


def _variables(case: EvaluationCase) -> dict[str, Any]:
    """The input variables the metric prompt was rendered with."""
    return {
        "input": case.input,
        "output": case.output,
        "context": case.context,
        "reference": case.reference,
    }


def _judge_json(score: MetricScore) -> dict[str, Any] | None:
    """The judge, the model it resolved to, its settings, and the system prompt."""
    if score.model is None:
        return None
    return {
        "name": score.judge_name,
        "version": score.judge_version,
        "model": score.model,
        "provider": score.provider,
        "temperature": score.temperature,
        "max_tokens": score.max_tokens,
        "system_prompt": score.system_prompt,
    }


def _prompt_json(score: MetricScore, variables: dict[str, Any]) -> dict[str, Any]:
    """The metric prompt template and the input variables it was rendered with."""
    return {"template": score.prompt_template, "variables": variables}
