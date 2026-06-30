"""FastAPI application assembly + cross-cutting handlers."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from arc_eval_service.core.config import get_settings
from arc_eval_service.core.deps import get_database
from arc_eval_service.core.errors import NotFoundError
from arc_eval_service.core.logging import configure_logging
from arc_eval_service.ingestion.router import router as ingestion_router

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

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        summary="Stores LLM interactions for quality evaluation in the ARC control plane.",
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

    app.include_router(ingestion_router)
    return app


app = create_app()
