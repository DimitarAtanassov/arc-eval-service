"""The wire contract for ``POST /v1/evaluate``.

This is the boundary ``arc-model-lab`` calls after inference: it sends a completed
interaction (:class:`EvaluateRequest`) and receives one score per metric
(:class:`EvaluateResponse`). These DTOs are the public shape of the service; the
internal judging types live in :mod:`arc_eval_service.domain.evaluation`.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

# Version of the POST /v1/evaluate request/response wire contract. Bump on any
# breaking change so a consumer can detect drift instead of failing silently.
CONTRACT_VERSION = "1.0.0"


class EvaluationMetadata(BaseModel):
    """Caller correlation ids. Extra keys are accepted and stored verbatim."""

    model_config = ConfigDict(extra="allow")

    inference_id: str | None = Field(
        default=None, description="Id of the inference record being evaluated."
    )
    model_id: str | None = Field(
        default=None, description="Id of the model under test that produced the output."
    )


class EvaluateRequest(BaseModel):
    """A completed interaction to score.

    The caller names the metrics to score explicitly; the service does not infer
    them from any task classification. Every field is required so a caller cannot
    submit a half-specified interaction and have the service guess the rest.
    """

    input_text: str = Field(
        ..., min_length=1, description="The original input (source text / question)."
    )
    output_text: str = Field(
        ..., min_length=1, description="The model output to evaluate."
    )
    prompt: str = Field(
        ...,
        min_length=1,
        description="The rendered prompt that produced the output, stored for audit.",
    )
    metrics: list[str] = Field(
        ...,
        min_length=1,
        description=(
            "Metrics to score the interaction against. An unknown metric name is "
            "rejected with 404."
        ),
    )
    metadata: EvaluationMetadata = Field(
        ...,
        description="Caller correlation ids (inference id, model id). May be empty.",
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
