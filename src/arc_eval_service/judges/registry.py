"""Judge registry (registry pattern, no plugin framework).

Maps a stable string key to a stateless judge strategy. A new metric becomes
available by registering it in :func:`default_registry`; nothing else changes.
"""

from __future__ import annotations

from arc_eval_service.core.errors import UnknownJudgeError
from arc_eval_service.judges.base import Judge
from arc_eval_service.judges.builtins import (
    AnswerRelevanceJudge,
    CustomJudge,
    FaithfulnessJudge,
    SafetyJudge,
)


class JudgeRegistry:
    """In-process registry of judge strategies keyed by name."""

    def __init__(self) -> None:
        self._judges: dict[str, Judge] = {}

    def register(self, judge: Judge) -> None:
        """Register ``judge`` under its ``name`` (rejecting duplicates)."""
        if judge.name in self._judges:
            msg = f"judge '{judge.name}' already registered"
            raise ValueError(msg)
        self._judges[judge.name] = judge

    def has(self, name: str) -> bool:
        """Return whether a judge is registered under ``name``."""
        return name in self._judges

    def get(self, name: str) -> Judge:
        """Return the judge for ``name`` or raise :class:`UnknownJudgeError`."""
        try:
            return self._judges[name]
        except KeyError as exc:
            raise UnknownJudgeError(name) from exc

    def available(self) -> list[Judge]:
        """Return all registered judges, ordered by name."""
        return [self._judges[name] for name in sorted(self._judges)]


def default_registry() -> JudgeRegistry:
    """Build the registry with all built-in judges registered."""
    registry = JudgeRegistry()
    for judge in (
        FaithfulnessJudge(),
        AnswerRelevanceJudge(),
        SafetyJudge(),
        CustomJudge(),
    ):
        registry.register(judge)
    return registry
