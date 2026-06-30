"""The judge's output contract: strict-JSON verdict parsing (pure).

Every metric is scored by asking the model to return JSON
``{"score": 0..1, "label": "...", "explanation": "..."}``. :func:`parse_verdict`
tolerates fenced/loose JSON so a chatty model still parses. This is the judging
mechanism's contract; it is independent of any specific metric's rubric.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from arc_eval_service.core.errors import EvaluationError

_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)

VERDICT_INSTRUCTION = (
    "Respond with ONLY a JSON object of the form "
    '{"score": <number between 0 and 1>, "label": "<short verdict>", '
    '"explanation": "<one concise sentence>"}. '
    "1 is best, 0 is worst. Do not add any text outside the JSON."
)


@dataclass(frozen=True, slots=True)
class Verdict:
    """A parsed judge outcome (score normalised to ``[0, 1]``)."""

    score: float
    label: str | None = None
    explanation: str | None = None


def parse_verdict(text: str) -> Verdict:
    """Parse a model's text into a :class:`Verdict`.

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
    return Verdict(
        score=score,
        label=str(label) if label is not None else None,
        explanation=str(explanation) if explanation is not None else None,
    )
