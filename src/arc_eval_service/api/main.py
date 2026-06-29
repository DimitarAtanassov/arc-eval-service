"""FastAPI application assembly + cross-cutting middleware/handlers."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from arc_telemetry import instrument_fastapi, setup_tracing
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from arc_eval_service.api.routes import router
from arc_eval_service.core.config import get_settings
from arc_eval_service.core.deps import get_store
from arc_eval_service.core.errors import (
    EvaluationError,
    NotFoundError,
    UnknownJudgeError,
    UnknownModelError,
)
from arc_eval_service.core.logging import configure_logging

logger = logging.getLogger("arc_eval_service.api")


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Release store-held resources (e.g. the Postgres pool) on shutdown."""
    yield
    await get_store().dispose()


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

    @app.exception_handler(NotFoundError)
    async def _not_found_handler(_request: Request, exc: NotFoundError) -> JSONResponse:
        logger.info(
            "resource not found",
            extra={"resource": exc.resource, "identifier": exc.identifier},
        )
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(UnknownJudgeError)
    @app.exception_handler(UnknownModelError)
    async def _unknown_ref_handler(
        _request: Request, exc: UnknownJudgeError | UnknownModelError
    ) -> JSONResponse:
        logger.info("unknown reference", extra={"name": exc.name})
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(EvaluationError)
    async def _evaluation_error_handler(
        _request: Request, exc: EvaluationError
    ) -> JSONResponse:
        logger.info("evaluation rejected", extra={"detail": str(exc)})
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    app.include_router(router)
    instrument_fastapi(app, excluded_urls="health")
    return app


app = create_app()
