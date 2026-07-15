"""The complete interaction the scoring core operates on.

The wire :class:`~arc_eval_service.api.schemas.EvaluateRequest` may carry only an
``inference_id`` to resolve, so its interaction fields are optional. Once resolved,
the input, output, and prompt are guaranteed present: this value object encodes
that invariant so the scoring service and the mappers never handle a
half-specified request, and so neither depends on how the interaction was obtained.
"""

from __future__ import annotations

from dataclasses import dataclass

from arc_eval_service.api.schemas import EvaluationMetadata


@dataclass(frozen=True, slots=True)
class ResolvedInteraction:
    """A fully-specified interaction to score: the text, the metrics, and correlation ids."""

    input_text: str
    output_text: str
    prompt: str
    metrics: tuple[str, ...]
    metadata: EvaluationMetadata
