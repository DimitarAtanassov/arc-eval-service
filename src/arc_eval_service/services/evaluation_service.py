from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from uuid import uuid4

from arc_eval_service.api.schemas import EvaluateResponse
from arc_eval_service.catalog import Catalog
from arc_eval_service.db.repositories import (
    EvalRequestRepository,
    EvaluationResultRepository,
)
from arc_eval_service.domain.errors import UnknownMetricError
from arc_eval_service.domain.evaluation import EvaluationCase, MetricScore
from arc_eval_service.judging.engine import JudgeEngine
from arc_eval_service.services import mapping
from arc_eval_service.services.interaction import Interaction

logger = logging.getLogger("arc_eval_service.services.evaluation_service")


@dataclass(frozen=True)
class ScoredEvaluation:
    """The result of an in-process evaluation: the persisted request id and the response."""

    request_id: str
    response: EvaluateResponse


class EvaluationService:
    """Scores one interaction across the requested metrics and stores the outcome."""

    def __init__(
        self,
        *,
        engine: JudgeEngine,
        library: Catalog,
        requests: EvalRequestRepository,
        results: EvaluationResultRepository,
    ) -> None:
        self._engine = engine
        self._library = library
        self._requests = requests
        self._results = results

    async def score(
        self, interaction: Interaction, *, correlation_id: str | None = None
    ) -> ScoredEvaluation:
        """Score the interaction, persist it, and return the request id alongside the response.

        Takes a complete Interaction (input, output, metrics), so the scoring core is
        the single path both the evaluate route and an experiment run reuse. Callers
        that need the eval_request_id (for example, an experiment run recording the
        association) read it from the result; the correlation_id joins the scoring logs
        to the caller's other hops.
        """
        metric_names = self._select_metrics(interaction)
        request_id = str(uuid4())
        case = mapping.build_case(interaction, request_id=request_id)

        scored = await asyncio.gather(
            *(
                self._engine.score(name, case, case_id=request_id)
                for name in metric_names
            )
        )

        await self._persist(
            request_id, interaction, case, scored, correlation_id=correlation_id
        )
        response = EvaluateResponse(
            results=[
                mapping.to_metric_result(score, library=self._library)
                for score in scored
                if score.error is None
            ]
        )
        return ScoredEvaluation(request_id=request_id, response=response)

    def _select_metrics(self, interaction: Interaction) -> tuple[str, ...]:
        """Validate and de-duplicate the caller's explicit metrics.

        Every requested metric must be defined in the catalog: an unknown name is
        a client error, raised as :class:`UnknownMetricError` (surfaced as 404)
        before anything is scored or persisted. The selection is deduplicated and
        order preserving.
        """
        selected = tuple(dict.fromkeys(interaction.metrics))
        unknown = [name for name in selected if name not in self._library.metrics]
        if unknown:
            raise UnknownMetricError(unknown)
        return selected

    async def _persist(
        self,
        request_id: str,
        interaction: Interaction,
        case: EvaluationCase,
        scored: list[MetricScore],
        *,
        correlation_id: str | None = None,
    ) -> None:
        """Store the interaction and every result. Best-effort: log and swallow."""
        new_request = mapping.new_eval_request(interaction, request_id=request_id)
        new_results = mapping.new_eval_results(
            scored,
            request_id=request_id,
            case=case,
            library=self._library,
        )
        try:
            async with self._requests.begin() as session:
                await self._requests.create(new_request, session=session)
                await self._results.create_many(new_results, session=session)
        except Exception:
            logger.exception(
                "failed to persist evaluation",
                extra={"eval_request_id": request_id, "correlation_id": correlation_id},
            )
