"""Traces routes: accept OTLP exports and serve assembled trace trees."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from arc_eval_service.core.config import Settings, get_settings
from arc_eval_service.core.deps import get_ingest_service, get_trace_service
from arc_eval_service.traces.ingest import IngestService
from arc_eval_service.traces.schemas import IngestResponse, Trace
from arc_eval_service.traces.service import TraceService
from arc_eval_service.traces.wire import OTLPTracePayload

router = APIRouter()

IngestDep = Annotated[IngestService, Depends(get_ingest_service)]
TraceDep = Annotated[TraceService, Depends(get_trace_service)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


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
    spans, headers, cases = ingest.parse(payload)
    await ingest.store(spans, headers)
    background.add_task(ingest.run, cases)
    return IngestResponse(accepted=len(cases), spans=len(spans))


@router.get("/v1/traces/{trace_id}", response_model=Trace, tags=["traces"])
async def get_trace(trace_id: str, service: TraceDep) -> Trace:
    """Return the full span tree for a trace from the trace store."""
    return await service.get_trace(trace_id)
