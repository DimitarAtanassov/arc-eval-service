"""FastAPI application assembly + cross-cutting middleware/handlers."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from arc_telemetry import instrument_fastapi, setup_tracing
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from arc_eval_service.core.config import get_settings
from arc_eval_service.core.deps import get_database
from arc_eval_service.core.errors import (
    EvaluationError,
    NotFoundError,
    UnknownMetricError,
    UnknownModelError,
)
from arc_eval_service.core.logging import configure_logging
from arc_eval_service.discovery.router import router as discovery_router
from arc_eval_service.evaluation.router import router as evaluation_router
from arc_eval_service.middleware import GzipRequestMiddleware
from arc_eval_service.traces.router import router as traces_router

logger = logging.getLogger("arc_eval_service.app")


class HealthResponse(BaseModel):
    """Liveness response."""

    status: str = "ok"
    service: str


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Release the database connection pool on shutdown."""
    yield
    await get_database().dispose()


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()
    configure_logging(level=settings.log_level)
    setup_tracing(service_name=settings.service_name)

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        summary="Online and offline AI quality evaluation for the ARC control plane.",
        lifespan=_lifespan,
    )

    @app.get("/health", response_model=HealthResponse, tags=["ops"])
    async def health() -> HealthResponse:
        return HealthResponse(status="ok", service=settings.service_name)

    @app.exception_handler(NotFoundError)
    async def _not_found_handler(_request: Request, exc: NotFoundError) -> JSONResponse:
        logger.info(
            "resource not found",
            extra={"resource": exc.resource, "identifier": exc.identifier},
        )
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(UnknownMetricError)
    @app.exception_handler(UnknownModelError)
    async def _unknown_ref_handler(
        _request: Request, exc: UnknownMetricError | UnknownModelError
    ) -> JSONResponse:
        logger.info("unknown reference", extra={"name": exc.name})
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(EvaluationError)
    async def _evaluation_error_handler(
        _request: Request, exc: EvaluationError
    ) -> JSONResponse:
        logger.info("evaluation rejected", extra={"detail": str(exc)})
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    app.include_router(evaluation_router)
    app.include_router(traces_router)
    app.include_router(discovery_router)
    # Decompress gzip request bodies (OTLP/HTTP exporters compress by default).
    app.add_middleware(GzipRequestMiddleware)
    # Exclude the OTLP ingest path from self-instrumentation: tracing the
    # trace-ingestion endpoint would emit a server span per ingest, which the
    # collector fans back here, ingesting again -- an unbounded feedback loop.
    instrument_fastapi(app, excluded_urls="health,v1/otlp/traces")
    return app


app = create_app()
