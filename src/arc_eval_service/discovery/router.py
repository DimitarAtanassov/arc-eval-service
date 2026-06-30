"""Discovery routes: list metrics and model profiles."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from arc_eval_service.core.deps import get_discovery_service
from arc_eval_service.discovery.schemas import MetricInfo, ModelProfileInfo
from arc_eval_service.discovery.service import DiscoveryService

router = APIRouter(tags=["discovery"])

DiscoveryDep = Annotated[DiscoveryService, Depends(get_discovery_service)]


@router.get("/v1/metrics", response_model=list[MetricInfo])
async def list_metrics(discovery: DiscoveryDep) -> list[MetricInfo]:
    """List the registered metrics and what each requires."""
    return discovery.metrics()


@router.get("/v1/models", response_model=list[ModelProfileInfo])
async def list_models(discovery: DiscoveryDep) -> list[ModelProfileInfo]:
    """List the configured model profiles (no secrets)."""
    return discovery.model_profiles()
