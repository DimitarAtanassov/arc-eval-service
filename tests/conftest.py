"""Shared test fixtures.

The DI factories in :mod:`arc_eval_service.core.deps` are cached singletons;
``reset_state`` clears them before every test. The ``client`` fixture overrides
the evaluation service to run on a **stub model** so no judge call hits the
network — judges and orchestration are exercised for real, the model is faked.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient

from arc_eval_service.api.main import create_app
from arc_eval_service.core import deps
from arc_eval_service.core.config import get_settings
from arc_eval_service.core.errors import ModelError, UnknownModelError
from arc_eval_service.ingest import OfflineIngestService
from arc_eval_service.models.base import JudgeModel, ModelCompletion, ModelSettings
from arc_eval_service.models.profiles import ModelProfile, ModelRegistry
from arc_eval_service.services.discovery import DiscoveryService
from arc_eval_service.services.evaluation import EvaluationService

GOOD_VERDICT = '{"score": 0.9, "label": "pass", "explanation": "looks good"}'


class StubModel(JudgeModel):
    """A judge model that returns canned text (or fails) without any network."""

    provider = "stub"

    def __init__(self, text: str, *, fail: bool = False) -> None:
        self.name = "stub-model"
        self._text = text
        self._fail = fail

    async def complete(
        self, *, system: str | None, prompt: str, settings: ModelSettings
    ) -> ModelCompletion:
        if self._fail:
            raise ModelError("stub model failure")
        return ModelCompletion(text=self._text, model=self.name)


class StubModelRegistry(ModelRegistry):
    """A registry with one ``default`` profile that resolves to a stub model."""

    def __init__(self, *, text: str = GOOD_VERDICT, fail: bool = False) -> None:
        super().__init__(
            [ModelProfile(name="default", provider="openai_compatible", model="stub")],
            default="default",
        )
        self._text = text
        self._fail = fail

    def resolve(
        self, name: str | None = None, *, model_override: str | None = None
    ) -> JudgeModel:
        if not self.has(name):
            raise UnknownModelError(name or "default")
        return StubModel(self._text, fail=self._fail)


def stub_service(*, text: str = GOOD_VERDICT, fail: bool = False) -> EvaluationService:
    """Build an evaluation service wired to the active store + a stub model."""
    return EvaluationService(
        store=deps.get_store(),
        judges=deps.get_judges(),
        models=StubModelRegistry(text=text, fail=fail),
    )


@pytest.fixture(autouse=True)
def reset_state() -> Iterator[None]:
    """Clear cached singletons so each test starts fresh."""
    caches = (
        deps.get_store,
        deps.get_span_store,
        deps.get_judges,
        deps.get_models,
        get_settings,
    )
    for cache in caches:
        cache.cache_clear()
    yield
    for cache in caches:
        cache.cache_clear()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """An httpx AsyncClient bound to the ASGI app, judging on a stub model."""
    app = create_app()
    app.dependency_overrides[deps.get_evaluation_service] = stub_service
    app.dependency_overrides[deps.get_discovery_service] = lambda: DiscoveryService(
        judges=deps.get_judges(), models=StubModelRegistry()
    )
    app.dependency_overrides[deps.get_offline_ingest_service] = lambda: (
        OfflineIngestService(
            evaluation=stub_service(),
            spans=deps.get_span_store(),
            self_service_name="arc-eval-service",
            default_judge="safety",
            default_model="default",
        )
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client
    app.dependency_overrides.clear()
