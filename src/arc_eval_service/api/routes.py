"""Route definitions only.

Routes delegate straight to the service layer and shape nothing themselves. No
orchestration, judging or persistence logic lives here. Selecting sync vs async
execution (or scheduling offline ingest) is request wiring, not business logic.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    status,
)

from arc_eval_service.api.schemas import (
    BatchEvaluateRequest,
    EvaluateRequest,
    HealthResponse,
    IngestResponse,
    RerunRequest,
)
from arc_eval_service.core.config import Settings, get_settings
from arc_eval_service.core.deps import (
    get_evaluation_service,
    get_offline_ingest_service,
    get_trace_service,
)
from arc_eval_service.ingest.otlp import OfflineIngestService, OTLPTracePayload
from arc_eval_service.schemas.models import (
    EvaluationRecord,
    ExecutionMode,
    JudgeInfo,
    ModelProfileInfo,
    Trace,
)
from arc_eval_service.services.evaluation import EvaluationService
from arc_eval_service.services.traces import TraceService

router = APIRouter()

ServiceDep = Annotated[EvaluationService, Depends(get_evaluation_service)]
IngestDep = Annotated[OfflineIngestService, Depends(get_offline_ingest_service)]
TraceDep = Annotated[TraceService, Depends(get_trace_service)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.get("/health", response_model=HealthResponse, tags=["ops"])
async def health(settings: SettingsDep) -> HealthResponse:
    """Liveness probe."""
    return HealthResponse(status="ok", service=settings.service_name)


@router.post("/v1/evaluate", response_model=EvaluationRecord, tags=["evaluations"])
async def evaluate(
    request: EvaluateRequest,
    service: ServiceDep,
    background: BackgroundTasks,
) -> EvaluationRecord:
    """Judge one interaction synchronously or asynchronously."""
    if request.mode is ExecutionMode.ASYNC:
        record = await service.submit(request)
        background.add_task(service.run_async, record.evaluation_id, request)
        return record
    return await service.evaluate(request)


@router.post(
    "/v1/evaluate/batch",
    response_model=list[EvaluationRecord],
    tags=["evaluations"],
)
async def evaluate_batch(
    request: BatchEvaluateRequest,
    service: ServiceDep,
    settings: SettingsDep,
) -> list[EvaluationRecord]:
    """Judge a batch of interactions synchronously, preserving order."""
    if len(request.items) > settings.max_batch_size:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"batch size {len(request.items)} exceeds "
            f"max_batch_size ({settings.max_batch_size})",
        )
    return await service.batch(request.items)


@router.get(
    "/v1/evaluations", response_model=list[EvaluationRecord], tags=["evaluations"]
)
async def list_evaluations(
    service: ServiceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[EvaluationRecord]:
    """List recent evaluation records, most recently created first."""
    return await service.recent(limit)


@router.get(
    "/v1/evaluations/{evaluation_id}",
    response_model=EvaluationRecord,
    tags=["evaluations"],
)
async def get_evaluation(evaluation_id: str, service: ServiceDep) -> EvaluationRecord:
    """Return a stored evaluation record by id."""
    return await service.get(evaluation_id)


@router.post(
    "/v1/evaluations/{evaluation_id}/rerun",
    response_model=EvaluationRecord,
    tags=["evaluations"],
)
async def rerun_evaluation(
    evaluation_id: str, request: RerunRequest, service: ServiceDep
) -> EvaluationRecord:
    """Re-judge a stored case, optionally with different judges/models."""
    return await service.rerun(evaluation_id, request.judges)


@router.get("/v1/judges", response_model=list[JudgeInfo], tags=["discovery"])
async def list_judges(service: ServiceDep) -> list[JudgeInfo]:
    """List the registered judges and what each requires."""
    return service.judges()


@router.get("/v1/models", response_model=list[ModelProfileInfo], tags=["discovery"])
async def list_models(service: ServiceDep) -> list[ModelProfileInfo]:
    """List the configured model profiles (no secrets)."""
    return service.model_profiles()


@router.post(
    "/v1/otlp/traces",
    response_model=IngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["ingest"],
)
async def ingest_traces(
    payload: OTLPTracePayload,
    ingest: IngestDep,
    settings: SettingsDep,
    background: BackgroundTasks,
) -> IngestResponse:
    """Accept an OTLP traces batch (from the collector): store spans, judge cases."""
    if not settings.ingest_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="offline ingestion is disabled",
        )
    spans, cases = ingest.parse(payload)
    await ingest.store(spans)
    background.add_task(ingest.run, cases)
    return IngestResponse(accepted=len(cases), spans=len(spans))


@router.get("/v1/traces/{trace_id}", response_model=Trace, tags=["traces"])
async def get_trace(trace_id: str, service: TraceDep) -> Trace:
    """Return the full span tree for a trace from the span store."""
    return await service.get_trace(trace_id)
