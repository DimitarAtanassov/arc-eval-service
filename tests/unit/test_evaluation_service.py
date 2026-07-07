"""Unit tests for the evaluation service: metric selection, mapping, and fail-open.

The judge engine and repositories are replaced with in-memory doubles, so these
tests exercise the service's own logic (which metrics run, how results are mapped,
that persistence failures are swallowed) without a model or a database.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from arc_eval_service.api.schemas import EvaluateRequest, EvaluationMetadata
from arc_eval_service.catalog import load_catalog
from arc_eval_service.db.records import NewEvalRequest, NewEvaluationResult
from arc_eval_service.db.repositories import (
    EvalRequestRepository,
    EvaluationResultRepository,
)
from arc_eval_service.domain.errors import UnknownMetricError
from arc_eval_service.domain.evaluation import EvaluationCase, MetricScore
from arc_eval_service.judging.engine import JudgeEngine
from arc_eval_service.services.evaluation_service import EvaluationService

pytestmark = pytest.mark.unit


def _ok(metric: str, *, score: float = 0.9) -> MetricScore:
    return MetricScore(
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


def _errored(metric: str) -> MetricScore:
    return MetricScore(
        metric=metric, score=0.0, passed=False, latency_ms=1.0, error="no judge model"
    )


class _FakeEngine(JudgeEngine):
    """Returns a canned result per metric; never calls a model."""

    def __init__(self, results: dict[str, MetricScore]) -> None:
        self._results = results

    async def score(
        self,
        metric: str,
        case: EvaluationCase,
        *,
        case_id: str,
        judge: str | None = None,
    ) -> MetricScore:
        return self._results[metric]


class _SpyRequestRepo(EvalRequestRepository):
    def __init__(self) -> None:
        self.created: list[NewEvalRequest] = []

    @asynccontextmanager
    async def begin(self) -> AsyncIterator[AsyncSession]:
        yield cast(AsyncSession, None)

    async def create(
        self, item: NewEvalRequest, *, session: AsyncSession | None = None
    ) -> None:
        self.created.append(item)


class _SpyResultRepo(EvaluationResultRepository):
    def __init__(self) -> None:
        self.created: list[NewEvaluationResult] = []

    async def create_many(
        self,
        items: Sequence[NewEvaluationResult],
        *,
        session: AsyncSession | None = None,
    ) -> None:
        self.created.extend(items)


class _FailingRequestRepo(EvalRequestRepository):
    def __init__(self) -> None:
        pass

    @asynccontextmanager
    async def begin(self) -> AsyncIterator[AsyncSession]:
        yield cast(AsyncSession, None)

    async def create(
        self, item: NewEvalRequest, *, session: AsyncSession | None = None
    ) -> None:
        raise RuntimeError("db down")


def _service(
    engine: JudgeEngine,
    *,
    requests: EvalRequestRepository | None = None,
    results: EvaluationResultRepository | None = None,
) -> EvaluationService:
    return EvaluationService(
        engine=engine,
        library=load_catalog(),
        requests=requests or _SpyRequestRepo(),
        results=results or _SpyResultRepo(),
    )


_DEFAULT_METRICS = ["faithfulness", "answer_relevance"]


def _request(*, metrics: list[str] | None = None) -> EvaluateRequest:
    return EvaluateRequest(
        input_text="the source article",
        output_text="the summary",
        prompt="Summarize:",
        metrics=metrics if metrics is not None else list(_DEFAULT_METRICS),
        metadata=EvaluationMetadata(inference_id="inf-1", model_id="mdl-1"),
    )


async def test_scored_metrics_are_returned_and_mapped() -> None:
    engine = _FakeEngine(
        {
            "faithfulness": _ok("faithfulness"),
            "answer_relevance": _ok("answer_relevance"),
        }
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
    assert {r.metric_name for r in results.created} == {
        "faithfulness",
        "answer_relevance",
    }
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
    assert faith_row.prompt is not None
    assert faith_row.prompt["template"] == "rubric for faithfulness"
    assert faith_row.prompt["variables"]["input"] == "the source article"
    assert faith_row.prompt["variables"]["output"] == "the summary"


async def test_only_requested_metrics_are_scored() -> None:
    engine = _FakeEngine({"faithfulness": _ok("faithfulness")})
    requests, results = _SpyRequestRepo(), _SpyResultRepo()
    service = _service(engine, requests=requests, results=results)

    response = await service.evaluate(_request(metrics=["faithfulness"]))

    # Only the metric the caller named is scored and persisted.
    assert {r.metric_name for r in response.results} == {"faithfulness"}
    assert {r.metric_name for r in results.created} == {"faithfulness"}


async def test_explicit_metrics_are_deduplicated() -> None:
    engine = _FakeEngine({"faithfulness": _ok("faithfulness")})
    results = _SpyResultRepo()
    service = _service(engine, results=results)

    response = await service.evaluate(
        _request(metrics=["faithfulness", "faithfulness"])
    )

    assert {r.metric_name for r in response.results} == {"faithfulness"}
    assert len(results.created) == 1


async def test_unknown_metric_raises_and_persists_nothing() -> None:
    requests, results = _SpyRequestRepo(), _SpyResultRepo()
    service = _service(_FakeEngine({}), requests=requests, results=results)

    with pytest.raises(UnknownMetricError) as exc_info:
        await service.evaluate(_request(metrics=["faithfulness", "does-not-exist"]))

    # The known metric is accepted; only the undefined one is reported, and the
    # request is rejected before anything is scored or persisted.
    assert exc_info.value.names == ("does-not-exist",)
    assert requests.created == []
    assert results.created == []


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
    assert all(
        r.prompt is not None and r.prompt["template"] is None for r in results.created
    )


async def test_persistence_failure_does_not_fail_the_request() -> None:
    engine = _FakeEngine(
        {
            "faithfulness": _ok("faithfulness"),
            "answer_relevance": _ok("answer_relevance"),
        }
    )
    service = _service(engine, requests=_FailingRequestRepo())

    response = await service.evaluate(_request())

    # Scores are still returned even though the observability write failed.
    assert {r.metric_name for r in response.results} == {
        "faithfulness",
        "answer_relevance",
    }
