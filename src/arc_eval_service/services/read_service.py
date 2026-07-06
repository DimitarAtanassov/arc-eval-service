"""Read (browse) access to persisted evaluations and the metric catalog.

A thin read orchestrator over the two repositories and the catalog. It is kept
separate from :class:`~arc_eval_service.services.evaluation_service.EvaluationService`
(the write path) so browsing shares no transaction policy with scoring: reads open
short-lived, transaction-free sessions.
"""

from __future__ import annotations

from dataclasses import dataclass

from arc_eval_service.catalog import Catalog
from arc_eval_service.catalog.metric.definition import MetricDefinition
from arc_eval_service.db.records import StoredEvalRequest, StoredEvaluationResult
from arc_eval_service.db.repositories import (
    EvalRequestRepository,
    EvaluationResultRepository,
)


@dataclass(frozen=True, slots=True)
class RequestWithResults:
    """One eval request paired with its metric scores."""

    request: StoredEvalRequest
    results: list[StoredEvaluationResult]


class ReadService:
    """Lists persisted requests and scores, and exposes the metric catalog."""

    def __init__(
        self,
        *,
        requests: EvalRequestRepository,
        results: EvaluationResultRepository,
        catalog: Catalog,
    ) -> None:
        self._requests = requests
        self._results = results
        self._catalog = catalog

    @property
    def metrics(self) -> dict[str, MetricDefinition]:
        """The metric definitions the service can score against."""
        return self._catalog.metrics

    async def list_requests(self, limit: int) -> list[StoredEvalRequest]:
        return await self._requests.list_recent(limit)

    async def get_request(self, request_id: str) -> RequestWithResults | None:
        """Return one request with its scores, or ``None`` when absent."""
        request = await self._requests.get(request_id)
        if request is None:
            return None
        results = await self._results.list_for_request(request_id)
        return RequestWithResults(request=request, results=results)

    async def list_results(
        self,
        limit: int,
        *,
        metric_name: str | None = None,
        model_id: str | None = None,
    ) -> list[StoredEvaluationResult]:
        return await self._results.list_recent(limit, metric_name=metric_name, model_id=model_id)
