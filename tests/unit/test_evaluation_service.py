"""Unit tests for the evaluation service: mapping, task routing, and fail-open.

The judge engine and repositories are replaced with in-memory doubles, so these
tests exercise the service's own logic (which metrics run, how results are mapped,
that persistence failures are swallowed) without a model or a database.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from arc_eval_service.db.repositories import (
    EvalRequestRepository,
    EvaluationResultRepository,
)
from arc_eval_service.evaluation.contract import EvaluateRequest, EvaluationMetadata
from arc_eval_service.evaluation.records import NewEvalRequest, NewEvaluationResult
from arc_eval_service.evaluation.schemas import EvaluationCase, EvaluationResult
from arc_eval_service.evaluation.service import EvaluationService
from arc_eval_service.judging.engine import JudgeEngine
from arc_eval_service.prompts.loader import load_library

pytestmark = pytest.mark.unit


def _ok(metric: str, *, score: float = 0.9) -> EvaluationResult:
    return EvaluationResult(
        metric=metric,
        model="stub-judge",
        provider="openai_compatible",
        judge_name="default",
        judge_version="v1",
        prompt_template=f"rubric for {metric}",
        system_prompt=f"rubric for {metric}\n\nRespond with JSON only.",
        temperature=0.0,
        max_tokens=1024,
        score=score,
        passed=True,
        label="pass",
        explanation="grounded",
        latency_ms=1.0,
        error=None,
    )


def _errored(metric: str) -> EvaluationResult:
    return EvaluationResult(
        metric=metric, score=0.0, passed=False, latency_ms=1.0, error="no judge model"
    )


class _FakeEngine(JudgeEngine):
    """Returns a canned result per metric; never calls a model."""

    def __init__(self, results: dict[str, EvaluationResult]) -> None:
        self._results = results

    async def score(
        self,
        metric: str,
        case: EvaluationCase,
        *,
        case_id: str,
        judge: str | None = None,
    ) -> EvaluationResult:
        return self._results[metric]


class _SpyRequestRepo(EvalRequestRepository):
    def __init__(self) -> None:
        self.created: list[NewEvalRequest] = []

    async def create(self, item: NewEvalRequest) -> None:
        self.created.append(item)


class _SpyResultRepo(EvaluationResultRepository):
    def __init__(self) -> None:
        self.created: list[NewEvaluationResult] = []

    async def create_many(self, items: Sequence[NewEvaluationResult]) -> None:
        self.created.extend(items)


class _FailingRequestRepo(EvalRequestRepository):
    def __init__(self) -> None:
        pass

    async def create(self, item: NewEvalRequest) -> None:
        raise RuntimeError("db down")


def _service(
    engine: JudgeEngine,
    *,
    requests: EvalRequestRepository | None = None,
    results: EvaluationResultRepository | None = None,
) -> EvaluationService:
    return EvaluationService(
        engine=engine,
        library=load_library(),
        requests=requests or _SpyRequestRepo(),
        results=results or _SpyResultRepo(),
    )


def _request(task_type: str = "summarization") -> EvaluateRequest:
    return EvaluateRequest(
        task_type=task_type,
        input_text="the source article",
        output_text="the summary",
        prompt="Summarize:",
        metadata=EvaluationMetadata(inference_id="inf-1", model_id="mdl-1"),
    )


async def test_scored_metrics_are_returned_and_mapped() -> None:
    engine = _FakeEngine(
        {"faithfulness": _ok("faithfulness"), "answer_relevance": _ok("answer_relevance")}
    )
    requests, results = _SpyRequestRepo(), _SpyResultRepo()
    service = _service(engine, requests=requests, results=results)

    response = await service.evaluate(_request())

    by_name = {r.metric_name: r for r in response.results}
    assert set(by_name) == {"faithfulness", "answer_relevance"}
    assert by_name["faithfulness"].score == 0.9
    assert by_name["faithfulness"].reasoning == "grounded"
    assert by_name["faithfulness"].evaluator_name == "faithfulness"
    assert by_name["faithfulness"].evaluator_version == "v1"
    # One request row plus one result row per metric were persisted with the ids.
    assert len(requests.created) == 1
    assert requests.created[0].inference_id == "inf-1"
    assert {r.metric_name for r in results.created} == {"faithfulness", "answer_relevance"}
    # Judge and prompt provenance are captured on each persisted result.
    faith_row = next(r for r in results.created if r.metric_name == "faithfulness")
    assert faith_row.judge == {
        "name": "default",
        "version": "v1",
        "model": "stub-judge",
        "provider": "openai_compatible",
        "temperature": 0.0,
        "max_tokens": 1024,
        "system_prompt": "rubric for faithfulness\n\nRespond with JSON only.",
    }
    assert faith_row.prompt["template"] == "rubric for faithfulness"
    assert faith_row.prompt["variables"]["input"] == "the source article"
    assert faith_row.prompt["variables"]["output"] == "the summary"


async def test_unknown_task_type_uses_default_metrics() -> None:
    engine = _FakeEngine(
        {"answer_relevance": _ok("answer_relevance"), "safety": _ok("safety")}
    )
    service = _service(engine)

    response = await service.evaluate(_request(task_type="question_answering"))

    assert {r.metric_name for r in response.results} == {"answer_relevance", "safety"}


async def test_errored_metrics_are_excluded_from_response_but_persisted() -> None:
    engine = _FakeEngine(
        {
            "faithfulness": _errored("faithfulness"),
            "answer_relevance": _errored("answer_relevance"),
        }
    )
    results = _SpyResultRepo()
    service = _service(engine, results=results)

    response = await service.evaluate(_request())

    assert response.results == []
    assert len(results.created) == 2
    assert all(r.error == "no judge model" for r in results.created)
    # An errored metric has no judge provenance and a null prompt template.
    assert all(r.judge is None for r in results.created)
    assert all(r.prompt["template"] is None for r in results.created)


async def test_persistence_failure_does_not_fail_the_request() -> None:
    engine = _FakeEngine(
        {"faithfulness": _ok("faithfulness"), "answer_relevance": _ok("answer_relevance")}
    )
    service = _service(engine, requests=_FailingRequestRepo())

    response = await service.evaluate(_request())

    # Scores are still returned even though the observability write failed.
    assert {r.metric_name for r in response.results} == {"faithfulness", "answer_relevance"}
