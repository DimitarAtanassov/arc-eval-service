"""FastAPI application assembly."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from arc_eval_service.api.dependencies import get_database
from arc_eval_service.api.errors import register_exception_handlers
from arc_eval_service.api.routes.evaluate import router as evaluate_router
from arc_eval_service.api.routes.health import router as health_router
from arc_eval_service.core.config import get_settings
from arc_eval_service.core.logging import configure_logging


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

    app.include_router(health_router)
    app.include_router(evaluate_router)
    register_exception_handlers(app)
    return app


app = create_app()


def run() -> None:
    """Serve the app on the configured host and port (container entrypoint)."""
    settings = get_settings()
    uvicorn.run(
        "arc_eval_service.app:app", host=settings.api_host, port=settings.api_port
    )


if __name__ == "__main__":
    run()
