"""The wire contract for ``POST /v1/evaluate``.

The caller sends a completed interaction (:class:`EvaluateRequest`: the input, the
output, and the metrics to score against) and receives one score per metric
(:class:`EvaluateResponse`). These DTOs are the public shape of the service; the
internal judging types live in :mod:`arc_eval_service.domain.evaluation`.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

# Version of the POST /v1/evaluate request/response wire contract. Bump on any
# breaking change so a consumer can detect drift instead of failing silently.
CONTRACT_VERSION = "1.0.0"


class EvaluateRequest(BaseModel):
    """A completed interaction to score: the input, the output, and the metrics.

    The caller always names the metrics explicitly; the service does not infer them
    from any task classification, and it scores the supplied text as given.
    """

    model_config = ConfigDict(extra="forbid")

    input_text: str = Field(
        min_length=1, description="The original input (source text or question)."
    )
    output_text: str = Field(min_length=1, description="The model output to evaluate.")
    metrics: list[str] = Field(
        ...,
        min_length=1,
        description=(
            "Metrics to score the interaction against. An unknown metric name is "
            "rejected with 404."
        ),
    )


class MetricResult(BaseModel):
    """One metric's score for the interaction."""

    metric_name: str
    score: float = Field(..., ge=0.0, le=1.0)
    reasoning: str | None = None
    evaluator_name: str
    evaluator_version: str | None = None


class EvaluateResponse(BaseModel):
    """The scored metrics for one interaction.

    Only metrics that scored successfully are returned. Metrics that failed (for
    example, no judge model is configured) are persisted with their error for
    observability but omitted here, so a caller never stores an infrastructure
    failure as a real score of zero.

    ``contract_version`` lets a consumer detect a wire-shape change instead of
    failing silently when the provider evolves the contract.
    """

    contract_version: str = Field(
        default=CONTRACT_VERSION,
        description="Version of the evaluate wire contract this response speaks.",
    )
    results: list[MetricResult]
