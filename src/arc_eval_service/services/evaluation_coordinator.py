"""The evaluate use-case: resolve the interaction, then score it.

The single entry point the ``POST /v1/evaluate`` route calls. It composes the
resolver (which may fetch from the lab) and the scorer, so the route stays a thin
one-call handler and neither collaborator depends on the other.
"""

from __future__ import annotations

from arc_eval_service.api.schemas import EvaluateRequest, EvaluateResponse
from arc_eval_service.services.evaluation_service import EvaluationService
from arc_eval_service.services.interaction_resolver import InteractionResolver


class EvaluationCoordinator:
    """Resolves an evaluate request (inline or by inference id), then scores it."""

    def __init__(
        self, *, resolver: InteractionResolver, evaluation: EvaluationService
    ) -> None:
        self._resolver = resolver
        self._evaluation = evaluation

    async def evaluate(
        self, request: EvaluateRequest, *, correlation_id: str | None = None
    ) -> EvaluateResponse:
        """Resolve the interaction and return the metrics that scored."""
        interaction = await self._resolver.resolve(
            request, correlation_id=correlation_id
        )
        scored = await self._evaluation.score(
            interaction, correlation_id=correlation_id
        )
        return scored.response
