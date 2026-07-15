"""Resolve an evaluate request into a complete interaction.

A request supplies its interaction one of two ways: inline (the text sent with the
request) or by reference (an ``inference_id`` fetched from arc-model-lab).
Resolution is the only part of the evaluate path that depends on the lab; keeping
it behind this seam leaves the scoring core (:class:`EvaluationService`) free of
that dependency and unit-testable without a network.
"""

from __future__ import annotations

import logging
from typing import Protocol

from arc_eval_service.api.schemas import EvaluateRequest
from arc_eval_service.clients.lab_inference_client import InferenceResult
from arc_eval_service.domain.errors import LabNotConfiguredError
from arc_eval_service.services.interaction import ResolvedInteraction

logger = logging.getLogger("arc_eval_service.services.interaction_resolver")


class InferenceReader(Protocol):
    """The inference-read seam the resolver depends on (LabInferenceClient satisfies it)."""

    async def get_inference(
        self, inference_id: str, *, correlation_id: str | None = None
    ) -> InferenceResult: ...


class InteractionResolver:
    """Turns an evaluate request (inline or by inference id) into a complete interaction."""

    def __init__(self, reader: InferenceReader | None) -> None:
        self._reader = reader

    async def resolve(
        self, request: EvaluateRequest, *, correlation_id: str | None = None
    ) -> ResolvedInteraction:
        """Resolve the interaction, fetching it from the lab when only an id is given.

        Inline requests never touch the lab. For a reference request, raises
        LabNotConfiguredError (503) when no lab is wired, and propagates
        InferenceNotFoundError (404) or LabInferenceError (502) from the fetch, so
        an unresolvable reference fails closed rather than scoring nothing.
        """
        if request.inference_id is None:
            return _inline(request)
        if self._reader is None:
            raise LabNotConfiguredError(
                "inference resolution requires the lab (ARC_LAB_SERVICE_URL is unset)"
            )
        logger.info(
            "resolving inference for evaluation",
            extra={
                "correlation_id": correlation_id,
                "inference_id": request.inference_id,
            },
        )
        inference = await self._reader.get_inference(
            request.inference_id, correlation_id=correlation_id
        )
        return _from_inference(request, inference)


def _inline(request: EvaluateRequest) -> ResolvedInteraction:
    """Build the interaction from an inline request.

    Precondition: the inline triple is present, which the request validator
    guarantees whenever no ``inference_id`` is set. The explicit guard documents
    that invariant and narrows the optional fields to ``str``.
    """
    if (
        request.input_text is None
        or request.output_text is None
        or request.prompt is None
    ):
        raise ValueError(
            "inline evaluation requires input_text, output_text, and prompt"
        )
    return ResolvedInteraction(
        input_text=request.input_text,
        output_text=request.output_text,
        prompt=request.prompt,
        metrics=tuple(request.metrics),
        metadata=request.metadata,
    )


def _from_inference(
    request: EvaluateRequest, inference: InferenceResult
) -> ResolvedInteraction:
    """Build the interaction from a fetched inference.

    The fetched inference is authoritative: its text is scored, and its own id and
    model id overwrite the request metadata so every persisted row links back to
    exactly what the lab produced (no caller-supplied drift).
    """
    metadata = request.metadata.model_copy(
        update={"inference_id": inference.id, "model_id": inference.model_id}
    )
    return ResolvedInteraction(
        input_text=inference.input_text,
        output_text=inference.output_text,
        prompt=inference.prompt,
        metrics=tuple(request.metrics),
        metadata=metadata,
    )
