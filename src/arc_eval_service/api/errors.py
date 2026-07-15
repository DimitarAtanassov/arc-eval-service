"""Maps domain errors to HTTP responses with safe, client-facing messages.

The judge engine captures per-metric scoring failures itself and degrades them to
errored results; these handlers cover the request-level errors that must reach the
client: an unknown metric or experiment (404), a name or model conflict (409), an
unconfigured lab (503), and an upstream lab failure (502). Client bodies stay safe,
so upstream and internal detail is logged, never echoed.
"""

from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse

from arc_eval_service.domain.errors import (
    ExperimentNameConflictError,
    ExperimentNotFoundError,
    InferenceNotFoundError,
    LabInferenceError,
    LabNotConfiguredError,
    LabRequestInvalidError,
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
    # The lab failed. Log the internal detail; return a fixed, safe body so the
    # upstream status or message is never echoed to our caller.
    logger.warning(
        "lab request failed", extra={"path": request.url.path, "detail": str(exc)}
    )
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={"detail": "upstream lab request failed"},
    )


async def _service_unavailable(request: Request, exc: Exception) -> Response:
    # A required dependency (the lab) is not configured. Log the detail; the
    # client gets a fixed, safe message rather than the config hint.
    logger.error(
        "experiment run unavailable",
        extra={"path": request.url.path, "detail": str(exc)},
    )
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "experiment runs are temporarily unavailable"},
    )


async def _unprocessable(request: Request, exc: Exception) -> Response:
    # The lab rejected the request as invalid (e.g. template variables): a caller
    # or config error, so surface a 422 with the lab's own detail (about the
    # caller's request, not lab internals).
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": str(exc)},
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
    app.add_exception_handler(InferenceNotFoundError, _not_found)
    app.add_exception_handler(ModelNotFoundError, _not_found)
    app.add_exception_handler(ExperimentNameConflictError, _conflict)
    app.add_exception_handler(ModelInactiveError, _conflict)
    app.add_exception_handler(LabInferenceError, _bad_gateway)
    app.add_exception_handler(LabNotConfiguredError, _service_unavailable)
    app.add_exception_handler(LabRequestInvalidError, _unprocessable)
    app.add_exception_handler(Exception, _unhandled)
