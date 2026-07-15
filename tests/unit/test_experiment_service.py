from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from arc_eval_service.api.schemas import EvaluateResponse
from arc_eval_service.clients.lab_inference_client import (
    InferenceResult,
    InferenceRunRequest,
)
from arc_eval_service.db.records import (
    NewExperiment,
    NewExperimentRun,
    StoredExperiment,
    StoredExperimentRun,
)
from arc_eval_service.domain.errors import (
    ExperimentNotFoundError,
    LabNotConfiguredError,
    ModelNotFoundError,
)
from arc_eval_service.domain.experiment import (
    ExperimentMetricAggregate,
    GenerationConfig,
)
from arc_eval_service.services.evaluation_service import ScoredEvaluation
from arc_eval_service.services.experiment_service import (
    ExperimentService,
    ExperimentStore,
    InferenceRunner,
    RunStore,
    Scorer,
)
from arc_eval_service.services.interaction import ResolvedInteraction

pytestmark = pytest.mark.unit

_CONFIG = {"temperature": 0.0, "max_output_tokens": 64}


def _stored_experiment(
    exp_id: str = "exp-1",
    name: str = "baseline",
    *,
    prompt_template: str | None = None,
    variables: dict[str, str] | None = None,
) -> StoredExperiment:
    return StoredExperiment(
        id=exp_id,
        name=name,
        model_name="candidate",
        generation_config=_CONFIG,
        prompt_template=prompt_template,
        variables=variables or {},
        description=None,
        created_at=datetime.now(UTC),
    )


def _inference() -> InferenceResult:
    return InferenceResult(
        id="inf-1",
        model_id="mdl-1",
        input_text="source",
        prompt="Summarize:",
        output_text="summary",
        latency_ms=10,
        prompt_tokens=1,
        completion_tokens=1,
        created_at=datetime.now(UTC),
    )


class _FakeExperiments:
    def __init__(
        self,
        stored: StoredExperiment | None = None,
        aggregates: list[ExperimentMetricAggregate] | None = None,
    ) -> None:
        self.stored = stored
        self.aggregates = aggregates or []
        self.created: list[NewExperiment] = []

    async def create(
        self, item: NewExperiment, *, session: Any = None
    ) -> StoredExperiment:
        self.created.append(item)
        return StoredExperiment(**item.model_dump())

    async def get(self, experiment_id: str) -> StoredExperiment | None:
        return self.stored

    async def list_recent(self, limit: int) -> list[StoredExperiment]:
        return [self.stored] if self.stored is not None else []

    async def aggregate_scores(
        self, experiment_id: str
    ) -> list[ExperimentMetricAggregate]:
        return self.aggregates


class _FakeRuns:
    def __init__(self) -> None:
        self.created: list[NewExperimentRun] = []

    async def create(
        self, item: NewExperimentRun, *, session: Any = None
    ) -> StoredExperimentRun:
        self.created.append(item)
        return StoredExperimentRun(**item.model_dump())


class _FakeLab:
    def __init__(
        self, result: InferenceResult | None = None, error: Exception | None = None
    ) -> None:
        self.result = result or _inference()
        self.error = error
        self.calls: list[InferenceRunRequest] = []

    async def run(
        self, request: InferenceRunRequest, *, correlation_id: str | None = None
    ) -> InferenceResult:
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        return self.result


class _FakeEval:
    def __init__(self, response: EvaluateResponse | None = None) -> None:
        self.response = response or EvaluateResponse(results=[])
        self.calls: list[ResolvedInteraction] = []

    async def score(
        self, interaction: ResolvedInteraction, *, correlation_id: str | None = None
    ) -> ScoredEvaluation:
        self.calls.append(interaction)
        return ScoredEvaluation(request_id="req-9", response=self.response)


def _service(
    *,
    experiments: ExperimentStore | None = None,
    runs: RunStore | None = None,
    lab_client: InferenceRunner | None = None,
    evaluation: Scorer | None = None,
    with_lab: bool = True,
) -> ExperimentService:
    return ExperimentService(
        experiments=experiments or _FakeExperiments(_stored_experiment()),
        runs=runs or _FakeRuns(),
        lab_client=lab_client
        if lab_client is not None
        else (_FakeLab() if with_lab else None),
        evaluation=evaluation or _FakeEval(),
    )


async def test_create_persists_and_returns_experiment() -> None:
    experiments = _FakeExperiments()
    service = _service(experiments=experiments)

    result = await service.create(
        name="baseline",
        model_name="candidate",
        generation_config=GenerationConfig(temperature=0.0, max_output_tokens=64),
    )

    assert result.name == "baseline"
    assert result.model_name == "candidate"
    assert experiments.created[0].generation_config == _CONFIG


async def test_get_returns_experiment() -> None:
    service = _service(experiments=_FakeExperiments(_stored_experiment()))
    assert (await service.get("exp-1")).id == "exp-1"


async def test_get_unknown_raises_not_found() -> None:
    service = _service(experiments=_FakeExperiments(None))
    with pytest.raises(ExperimentNotFoundError):
        await service.get("missing")


async def test_list_recent_returns_experiments() -> None:
    service = _service(experiments=_FakeExperiments(_stored_experiment()))
    assert len(await service.list_recent(10)) == 1


async def test_run_requires_a_lab_client() -> None:
    service = _service(with_lab=False)
    with pytest.raises(LabNotConfiguredError):
        await service.run("exp-1", "text", metrics=None)


async def test_run_unknown_experiment_raises_not_found() -> None:
    service = _service(experiments=_FakeExperiments(None))
    with pytest.raises(ExperimentNotFoundError):
        await service.run("missing", "text")


async def test_run_without_metrics_skips_evaluation() -> None:
    runs = _FakeRuns()
    evaluation = _FakeEval()
    service = _service(runs=runs, evaluation=evaluation)

    result = await service.run("exp-1", "text", metrics=None)

    assert result.evaluation is None
    assert result.eval_request_id is None
    assert evaluation.calls == []
    assert runs.created[0].eval_request_id is None


async def test_run_with_metrics_scores_and_links() -> None:
    runs = _FakeRuns()
    evaluation = _FakeEval()
    lab = _FakeLab()
    service = _service(runs=runs, evaluation=evaluation, lab_client=lab)

    result = await service.run("exp-1", "text", metrics=["faithfulness"])

    assert result.eval_request_id == "req-9"
    assert result.evaluation is not None
    assert runs.created[0].eval_request_id == "req-9"
    assert runs.created[0].inference_id == "inf-1"
    assert lab.calls[0].model_name == "candidate"
    assert evaluation.calls[0].metadata.inference_id == "inf-1"


async def test_run_propagates_model_not_found() -> None:
    runs = _FakeRuns()
    service = _service(
        runs=runs, lab_client=_FakeLab(error=ModelNotFoundError("candidate"))
    )

    with pytest.raises(ModelNotFoundError):
        await service.run("exp-1", "text", metrics=["faithfulness"])

    assert runs.created == []


async def test_results_aggregates_metrics() -> None:
    aggregates = [
        ExperimentMetricAggregate(
            metric_name="faithfulness", average_score=0.8, evaluated_count=2
        )
    ]
    service = _service(experiments=_FakeExperiments(_stored_experiment(), aggregates))

    results = await service.results("exp-1")

    assert results.experiment_id == "exp-1"
    assert results.metrics[0].metric_name == "faithfulness"


async def test_compare_returns_both_experiments() -> None:
    aggregates = [
        ExperimentMetricAggregate(
            metric_name="faithfulness", average_score=0.8, evaluated_count=1
        )
    ]
    service = _service(experiments=_FakeExperiments(_stored_experiment(), aggregates))

    compared = await service.compare("exp-1", "exp-1")

    assert len(compared) == 2


async def test_create_stores_prompt_template_and_variables() -> None:
    experiments = _FakeExperiments()
    service = _service(experiments=experiments)

    await service.create(
        name="translate-fr",
        model_name="candidate",
        generation_config=GenerationConfig(temperature=0.0, max_output_tokens=64),
        prompt_template="translate",
        variables={"target_language": "French"},
    )

    assert experiments.created[0].prompt_template == "translate"
    assert experiments.created[0].variables == {"target_language": "French"}


async def test_run_forwards_prompt_template_and_variables_to_lab() -> None:
    lab = _FakeLab()
    stored = _stored_experiment(
        prompt_template="translate", variables={"target_language": "French"}
    )
    service = _service(experiments=_FakeExperiments(stored), lab_client=lab)

    await service.run("exp-1", "hola", metrics=None)

    assert lab.calls[0].prompt_template == "translate"
    assert lab.calls[0].variables == {"target_language": "French"}
