"""Discovery service: read-only metadata about judges and model profiles.

Pure delegation to the registries plus DTO shaping; it never runs a judge or a
model. Kept separate from :class:`~arc_eval_service.services.evaluation.EvaluationService`
so the orchestrator owns only orchestration (no feature envy on the registries).
"""

from __future__ import annotations

from arc_eval_service.judges.registry import JudgeRegistry
from arc_eval_service.models.profiles import ModelRegistry
from arc_eval_service.schemas.models import JudgeInfo, ModelProfileInfo


class DiscoveryService:
    """Exposes what can be evaluated and on which model profiles."""

    def __init__(self, *, judges: JudgeRegistry, models: ModelRegistry) -> None:
        self._judges = judges
        self._models = models

    def judges(self) -> list[JudgeInfo]:
        """Return discovery metadata for every registered judge."""
        return [
            JudgeInfo(name=j.name, description=j.description, requires=list(j.requires))
            for j in self._judges.available()
        ]

    def model_profiles(self) -> list[ModelProfileInfo]:
        """Return discovery metadata for every configured model profile."""
        return self._models.list_profiles()
