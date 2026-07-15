"""The wire contract for ``POST /v1/evaluate``.

This is the boundary ``arc-model-lab`` calls after inference: it sends a completed
interaction (:class:`EvaluateRequest`) and receives one score per metric
(:class:`EvaluateResponse`). These DTOs are the public shape of the service; the
internal judging types live in :mod:`arc_eval_service.domain.evaluation`.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

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

    The interaction is supplied one of two ways, and exactly one must be used:
    inline (``input_text``, ``output_text``, and ``prompt`` together), or by
    reference (an ``inference_id`` the service resolves from arc-model-lab). The
    caller always names the metrics explicitly; the service does not infer them
    from any task classification.
    """

    inference_id: str | None = Field(
        default=None,
        min_length=1,
        description=(
            "Resolve the interaction from arc-model-lab by this inference id instead "
            "of sending it inline. Mutually exclusive with input_text/output_text/prompt."
        ),
    )
    input_text: str | None = Field(
        default=None,
        min_length=1,
        description=(
            "The original input (source text / question). Required unless "
            "inference_id is given."
        ),
    )
    output_text: str | None = Field(
        default=None,
        min_length=1,
        description="The model output to evaluate. Required unless inference_id is given.",
    )
    prompt: str | None = Field(
        default=None,
        min_length=1,
        description=(
            "The rendered prompt that produced the output, stored for audit. "
            "Required unless inference_id is given."
        ),
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
        default_factory=EvaluationMetadata,
        description="Caller correlation ids (inference id, model id). May be empty.",
    )

    @model_validator(mode="after")
    def _reference_xor_inline(self) -> EvaluateRequest:
        inline_fields = (self.input_text, self.output_text, self.prompt)
        any_inline = any(field is not None for field in inline_fields)
        all_inline = all(field is not None for field in inline_fields)
        if self.inference_id is not None:
            if any_inline:
                raise ValueError(
                    "provide either inference_id or the inline interaction, not both"
                )
            return self
        if not all_inline:
            raise ValueError(
                "provide inference_id, or all of input_text, output_text, and prompt"
            )
        return self


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
