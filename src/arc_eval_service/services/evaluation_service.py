from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from uuid import uuid4

from arc_eval_service.api.schemas import EvaluateRequest, EvaluateResponse
from arc_eval_service.catalog import Catalog
from arc_eval_service.db.repositories import (
    EvalRequestRepository,
    EvaluationResultRepository,
)
from arc_eval_service.domain.errors import UnknownMetricError
from arc_eval_service.domain.evaluation import EvaluationCase, MetricScore
from arc_eval_service.judging.engine import JudgeEngine
from arc_eval_service.services import mapping

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

    async def score(self, request: EvaluateRequest) -> ScoredEvaluation:
        """Score the interaction, persist it, and return the request id alongside the response.

        Callers that need the eval_request_id (for example, experiment runs that must
        record the association) use this method. The public POST /v1/evaluate route
        delegates to evaluate(), which discards the id.
        """
        metric_names = self._select_metrics(request)
        request_id = str(uuid4())
        case = mapping.build_case(request, request_id=request_id)

        scored = await asyncio.gather(
            *(
                self._engine.score(name, case, case_id=request_id)
                for name in metric_names
            )
        )

        await self._persist(request_id, request, case, scored)
        response = EvaluateResponse(
            results=[
                mapping.to_metric_result(score, library=self._library)
                for score in scored
                if score.error is None
            ]
        )
        return ScoredEvaluation(request_id=request_id, response=response)

    async def evaluate(self, request: EvaluateRequest) -> EvaluateResponse:
        """Score the interaction, persist it, and return the successful metrics.

        The public endpoint delegate: discards the internal request id.
        """
        return (await self.score(request)).response

    def _select_metrics(self, request: EvaluateRequest) -> tuple[str, ...]:
        """Validate and de-duplicate the caller's explicit metrics.

        Every requested metric must be defined in the catalog: an unknown name is
        a client error, raised as :class:`UnknownMetricError` (surfaced as 404)
        before anything is scored or persisted. The selection is deduplicated and
        order preserving.
        """
        selected = tuple(dict.fromkeys(request.metrics))
        unknown = [name for name in selected if name not in self._library.metrics]
        if unknown:
            raise UnknownMetricError(unknown)
        return selected

    async def _persist(
        self,
        request_id: str,
        request: EvaluateRequest,
        case: EvaluationCase,
        scored: list[MetricScore],
    ) -> None:
        """Store the interaction and every result. Best-effort: log and swallow."""
        new_request = mapping.new_eval_request(request, request_id=request_id)
        new_results = mapping.new_eval_results(
            scored,
            request_id=request_id,
            request=request,
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
                extra={"eval_request_id": request_id},
            )
