from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse

from arc_eval_service.domain.errors import (
    ExperimentNameConflictError,
    ExperimentNotFoundError,
    LabInferenceError,
    ModelInactiveError,
    ModelNotFoundError,
    UnknownMetricError,
)

logger = logging.getLogger("arc_eval_service.api.errors")


async def _unknown_metric(request: Request, exc: Exception) -> Response:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": str(exc) or "unknown metric"},
    )


async def _not_found(request: Request, exc: Exception) -> Response:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": str(exc)},
    )


async def _conflict(request: Request, exc: Exception) -> Response:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": str(exc)},
    )


async def _bad_gateway(request: Request, exc: Exception) -> Response:
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={"detail": str(exc) or "upstream lab request failed"},
    )


async def _unhandled(request: Request, exc: Exception) -> Response:
    """Last-resort boundary: log with a correlation id, return a safe 500 body.

    The real cause stays in the server log (keyed by ``correlation_id``); the
    client gets a generic message and the same id to quote in a support request.
    """
    correlation_id = str(uuid4())
    logger.exception(
        "unhandled error",
        extra={
            "correlation_id": correlation_id,
            "path": request.url.path,
            "method": request.method,
        },
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "internal server error", "correlation_id": correlation_id},
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(UnknownMetricError, _unknown_metric)
    app.add_exception_handler(ExperimentNotFoundError, _not_found)
    app.add_exception_handler(ModelNotFoundError, _not_found)
    app.add_exception_handler(ExperimentNameConflictError, _conflict)
    app.add_exception_handler(ModelInactiveError, _conflict)
    app.add_exception_handler(LabInferenceError, _bad_gateway)
    app.add_exception_handler(Exception, _unhandled)
