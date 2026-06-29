"""Judge strategy interface + shared verdict parsing (functional core).

A judge is a pure pair of functions: ``build_prompt`` renders the case into a
``(system, user)`` message, and ``parse`` turns the model's text back into a
:class:`JudgeVerdict`. Neither touches the network or the database — the
orchestrator (the imperative shell) runs the model between them. This keeps every
judge trivially unit-testable without a model.

Built-in judges share one output contract: the model must return JSON
``{"score": 0..1, "label": "...", "explanation": "..."}``. :func:`parse_verdict`
tolerates fenced/loose JSON so a chatty model still parses.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from arc_eval_service.core.errors import EvaluationError
from arc_eval_service.schemas.models import ConfigValue, EvaluationCase

_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


@dataclass(frozen=True, slots=True)
class JudgePrompt:
    """The rendered messages handed to a judge model."""

    user: str
    system: str | None = None


@dataclass(frozen=True, slots=True)
class JudgeVerdict:
    """A parsed judge outcome (score normalised to ``[0, 1]``)."""

    score: float
    label: str | None = None
    explanation: str | None = None


@runtime_checkable
class Judge(Protocol):
    """A pure scoring strategy executed on a judge model."""

    name: str
    description: str
    requires: tuple[str, ...]
    default_threshold: float

    def build_prompt(
        self, case: EvaluationCase, config: Mapping[str, ConfigValue]
    ) -> JudgePrompt: ...

    def parse(self, text: str) -> JudgeVerdict: ...


def parse_verdict(text: str) -> JudgeVerdict:
    """Parse a model's text into a :class:`JudgeVerdict`.

    Raises:
        EvaluationError: no JSON object, or no usable ``score``.
    """
    match = _JSON_OBJECT.search(text or "")
    if match is None:
        raise EvaluationError("judge model returned no JSON verdict")
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise EvaluationError(f"judge verdict is not valid JSON: {exc}") from exc

    raw = payload.get("score")
    if not isinstance(raw, int | float) or isinstance(raw, bool):
        raise EvaluationError("judge verdict missing a numeric 'score'")
    score = max(0.0, min(1.0, float(raw)))

    label = payload.get("label")
    explanation = payload.get("explanation")
    return JudgeVerdict(
        score=score,
        label=str(label) if label is not None else None,
        explanation=str(explanation) if explanation is not None else None,
    )


_VERDICT_INSTRUCTION = (
    "Respond with ONLY a JSON object of the form "
    '{"score": <number between 0 and 1>, "label": "<short verdict>", '
    '"explanation": "<one concise sentence>"}. '
    "1 is best, 0 is worst. Do not add any text outside the JSON."
)


class LLMJudge(ABC):
    """Base for built-in judges: shared parsing + the JSON verdict contract.

    Structurally a :class:`Judge` (it does not inherit the Protocol — that would
    clash class vars with the Protocol's instance vars). Subclasses set the class
    attributes and implement :meth:`_instructions` (the rubric) and :meth:`_render`
    (how the case is laid out). The system prompt and the strict-JSON instruction
    are added here once (DRY).
    """

    name: str
    description: str
    requires: tuple[str, ...] = ()
    default_threshold: float = 0.5

    @abstractmethod
    def _instructions(self, config: Mapping[str, ConfigValue]) -> str:
        """Return the rubric: what this judge is grading and how."""

    @abstractmethod
    def _render(self, case: EvaluationCase) -> str:
        """Return the case laid out for the model to grade."""

    def build_prompt(
        self, case: EvaluationCase, config: Mapping[str, ConfigValue]
    ) -> JudgePrompt:
        system = f"{self._instructions(config)}\n\n{_VERDICT_INSTRUCTION}"
        return JudgePrompt(system=system, user=self._render(case))

    def parse(self, text: str) -> JudgeVerdict:
        return parse_verdict(text)
