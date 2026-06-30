"""Discovery service: read-only metadata about metrics and model profiles.

Pure delegation to the registries plus DTO shaping; it never scores anything. It
maps the model profiles to a secret-free view, so credentials never leak through
the discovery surface.
"""

from __future__ import annotations

from arc_eval_service.discovery.schemas import MetricInfo, ModelProfileInfo
from arc_eval_service.judging.profiles import ModelRegistry
from arc_eval_service.metrics.registry import MetricRegistry


class DiscoveryService:
    """Exposes what can be evaluated and on which model profiles."""

    def __init__(self, *, metrics: MetricRegistry, models: ModelRegistry) -> None:
        self._metrics = metrics
        self._models = models

    def metrics(self) -> list[MetricInfo]:
        """Return discovery metadata for every registered metric."""
        return [
            MetricInfo(
                name=m.name, description=m.description, requires=list(m.requires)
            )
            for m in self._metrics.available()
        ]

    def model_profiles(self) -> list[ModelProfileInfo]:
        """Return discovery metadata for every configured model profile."""
        return [
            ModelProfileInfo(
                name=p.name, provider=p.provider, model=p.model, base_url=p.base_url
            )
            for p in self._models.profiles()
        ]
