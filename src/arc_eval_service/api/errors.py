"""Maps domain errors to HTTP responses with safe, client-facing messages.

The judge engine captures per-metric scoring failures itself and degrades them to
errored results. These handlers cover the request-level validation errors that
must instead reach the client: an explicitly requested metric the catalog does
not define.
"""

from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse

from arc_eval_service.domain.errors import UnknownMetricError

logger = logging.getLogger("arc_eval_service.api.errors")


async def _unknown_metric(request: Request, exc: Exception) -> Response:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": str(exc) or "unknown metric"},
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
    app.add_exception_handler(Exception, _unhandled)
