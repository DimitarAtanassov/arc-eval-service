"""Liveness route."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from arc_eval_service.core.config import get_settings

router = APIRouter(tags=["ops"])


class HealthResponse(BaseModel):
    """Liveness response."""

    status: str = "ok"
    service: str


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Report that the service is up."""
    return HealthResponse(status="ok", service=get_settings().service_name)
