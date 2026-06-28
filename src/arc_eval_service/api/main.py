"""FastAPI application assembly + cross-cutting middleware/handlers."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from arc_eval_service.api.routes import router
from arc_eval_service.core.config import get_settings
from arc_eval_service.core.errors import NotFoundError, UnknownEvaluatorError
from arc_eval_service.core.logging import configure_logging
from arc_eval_service.observability.tracing import setup_tracing

logger = logging.getLogger("arc_eval_service.api")


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()
    configure_logging(level=settings.log_level)
    setup_tracing(service_name=settings.service_name)

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        summary="Online and offline AI quality evaluation for the ARC control plane.",
    )

    @app.exception_handler(NotFoundError)
    async def _not_found_handler(_request: Request, exc: NotFoundError) -> JSONResponse:
        logger.info(
            "resource not found",
            extra={"resource": exc.resource, "identifier": exc.identifier},
        )
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(UnknownEvaluatorError)
    async def _unknown_evaluator_handler(
        _request: Request, exc: UnknownEvaluatorError
    ) -> JSONResponse:
        logger.info("unknown evaluator", extra={"evaluator_name": exc.name})
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    app.include_router(router)
    return app


app = create_app()
