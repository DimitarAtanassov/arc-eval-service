"""FastAPI application assembly."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel

from arc_eval_service.core.config import get_settings
from arc_eval_service.core.deps import get_database
from arc_eval_service.core.logging import configure_logging
from arc_eval_service.evaluation.router import router as evaluation_router


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
        summary="Scores LLM interactions for quality in the ARC control plane.",
        lifespan=_lifespan,
    )

    @app.get("/health", response_model=HealthResponse, tags=["ops"])
    async def health() -> HealthResponse:
        return HealthResponse(status="ok", service=settings.service_name)

    app.include_router(evaluation_router)
    return app


app = create_app()
