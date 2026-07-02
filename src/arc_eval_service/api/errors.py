"""Maps domain errors to HTTP responses with safe, client-facing messages.

The judge engine captures per-metric scoring failures itself and degrades them to
errored results. These handlers cover the request-level validation errors that
must instead reach the client: an explicitly requested metric the catalog does
not define.
"""

from __future__ import annotations

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse

from arc_eval_service.domain.errors import UnknownMetricError


async def _unknown_metric(request: Request, exc: Exception) -> Response:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": str(exc) or "unknown metric"},
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(UnknownMetricError, _unknown_metric)
