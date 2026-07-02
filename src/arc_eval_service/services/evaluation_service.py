"""Evaluation orchestration: score one interaction and persist the outcome.

The service is the whole job of ``POST /v1/evaluate``:

1. pick the metrics for the request's ``task_type`` (:mod:`services.policy`);
2. score them concurrently via the judge engine (best-effort per metric);
3. persist the interaction and every result, including failures, via the
   :mod:`services.mapping` record builders;
4. return only the metrics that scored successfully.

Scoring never raises: the judge engine degrades a failed metric to an errored
score, so one bad metric (or a missing judge model) cannot fail the request.
Persistence is best-effort too: a failed observability write is logged, not
surfaced, so the caller still gets its scores.
"""

from __future__ import annotations

import asyncio
import logging
from uuid import uuid4

from arc_eval_service.api.schemas import EvaluateRequest, EvaluateResponse
from arc_eval_service.catalog import Catalog
from arc_eval_service.db.repositories import (
    EvalRequestRepository,
    EvaluationResultRepository,
)
from arc_eval_service.domain.evaluation import EvaluationCase, MetricScore
from arc_eval_service.judging.engine import JudgeEngine
from arc_eval_service.services import mapping, policy

logger = logging.getLogger("arc_eval_service.services.evaluation_service")


class EvaluationService:
    """Scores one interaction across its task's metrics and stores the outcome."""

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

    async def evaluate(self, request: EvaluateRequest) -> EvaluateResponse:
        """Score the interaction, persist it, and return the successful metrics."""
        request_id = str(uuid4())
        metric_names = policy.metrics_for(request.task_type)
        case = mapping.build_case(request, request_id=request_id)

        scored = await asyncio.gather(
            *(
                self._engine.score(name, case, case_id=request_id)
                for name in metric_names
            )
        )

        await self._persist(request_id, request, case, scored)
        return EvaluateResponse(
            results=[
                mapping.to_metric_result(score, library=self._library)
                for score in scored
                if score.error is None
            ]
        )

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
            await self._requests.create(new_request)
            await self._results.create_many(new_results)
        except Exception:
            logger.exception(
                "failed to persist evaluation",
                extra={"eval_request_id": request_id},
            )
