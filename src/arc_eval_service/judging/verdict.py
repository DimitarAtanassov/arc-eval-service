"""The judge's structured output: a Pydantic verdict (schema and parser).

Every metric is scored by asking the judge model for a structured object
``{"score", "label", "explanation"}`` via the provider's structured-output
(JSON-schema) mode, so no free-text output instruction is needed. :class:`Verdict`
*is* the schema handed to the model and the shape parsed back; its field
descriptions carry the guidance the model needs (for example that ``1`` is best).
:func:`parse_verdict` still extracts the first JSON object so a chatty or
non-structured endpoint parses.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from arc_eval_service.domain.errors import EvaluationError

_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


class Verdict(BaseModel):
    """A judge outcome; doubles as the structured-output schema for the model."""

    model_config = ConfigDict(frozen=True)

    score: float = Field(description="Quality in [0, 1]; 1 is best, 0 is worst.")
    label: str | None = Field(default=None, description="A short verdict.")
    explanation: str | None = Field(
        default=None, description="One concise sentence explaining the score."
    )

    @field_validator("score", mode="before")
    @classmethod
    def _clamp_unit_interval(cls, value: object) -> float:
        """Require a numeric score and clamp it into ``[0, 1]``."""
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError("score must be numeric")
        return max(0.0, min(1.0, float(value)))


def parse_verdict(text: str) -> Verdict:
    """Parse a model's text into a :class:`Verdict`.

    Prefers a structured response, but extracts the first JSON object so a chatty
    or fenced reply still parses.

    Raises:
        EvaluationError: no JSON object, or no usable numeric ``score``.
    """
    match = _JSON_OBJECT.search(text or "")
    if match is None:
        raise EvaluationError("judge model returned no JSON verdict")
    try:
        return Verdict.model_validate_json(match.group(0))
    except ValidationError as exc:
        raise EvaluationError(f"invalid judge verdict: {exc}") from exc
