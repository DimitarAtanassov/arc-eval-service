from __future__ import annotations

import logging
from datetime import datetime
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from arc_eval_service.domain.errors import (
    LabInferenceError,
    LabRequestInvalidError,
    ModelInactiveError,
    ModelNotFoundError,
)
from arc_eval_service.domain.experiment import GenerationConfig

_INFERENCE_PATH = "/v1/inference:run"

logger = logging.getLogger("arc_eval_service.clients.lab_inference_client")


class LabInferenceSettings(BaseSettings):
    """Environment-driven configuration for the arc-model-lab integration.

    Namespaced under ARC_LAB_ so it composes with the service's ARC_ settings
    without touching them. An empty service_url means the lab is not wired and
    experiment runs will fail with a clear error.
    """

    model_config = SettingsConfigDict(
        env_prefix="ARC_LAB_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    service_url: str = ""
    timeout_seconds: float = 120.0


class InferenceRunRequest(BaseModel):
    """The outbound body for POST /v1/inference:run."""

    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    model_name: str
    input_text: str
    generation_config: GenerationConfig
    allow_inactive: bool = True
    prompt_template: str | None = None
    variables: dict[str, str] = Field(default_factory=dict)


class InferenceResult(BaseModel):
    """The lab's response for one completed inference."""

    model_config = ConfigDict(protected_namespaces=())

    id: str
    model_id: str
    input_text: str
    prompt: str
    output_text: str
    latency_ms: int
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    created_at: datetime


class LabInferenceClient:
    """Asynchronous client for the arc-model-lab /v1/inference:run endpoint."""

    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self._http = http_client

    async def run(
        self,
        request: InferenceRunRequest,
        *,
        correlation_id: str | None = None,
    ) -> InferenceResult:
        """Run one inference via the lab.

        Raises ModelNotFoundError on 404 (unknown model or prompt template),
        ModelInactiveError on 409 (model deactivated), LabRequestInvalidError on 422
        (bad template variables or config, a caller error), and LabInferenceError for
        every other failure so the experiment service has typed signals to surface.
        """
        cid = correlation_id or str(uuid4())
        logger.info(
            "calling lab inference",
            extra={
                "correlation_id": cid,
                "model_name": request.model_name,
                "path": _INFERENCE_PATH,
            },
        )
        try:
            response = await self._http.post(
                _INFERENCE_PATH,
                json=request.model_dump(mode="json"),
                headers={"X-Correlation-ID": cid},
            )
        except httpx.ConnectError as exc:
            raise LabInferenceError("lab connection failed") from exc
        except httpx.HTTPError as exc:
            raise LabInferenceError("lab request failed") from exc

        if response.status_code == httpx.codes.NOT_FOUND:
            raise ModelNotFoundError(request.model_name)
        if response.status_code == httpx.codes.CONFLICT:
            raise ModelInactiveError(request.model_name)
        if response.status_code == httpx.codes.UNPROCESSABLE_ENTITY:
            raise LabRequestInvalidError(
                _detail(response) or "lab rejected the request as invalid"
            )

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise LabInferenceError(f"lab returned {response.status_code}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise LabInferenceError("lab returned a non-JSON response") from exc

        try:
            return InferenceResult.model_validate(payload)
        except ValidationError as exc:
            raise LabInferenceError("lab returned an unexpected schema") from exc

    async def aclose(self) -> None:
        await self._http.aclose()


def build_lab_inference_client(
    settings: LabInferenceSettings,
) -> LabInferenceClient | None:
    """Build a client from settings, or None when no service url is configured."""
    if not settings.service_url:
        return None
    http_client = httpx.AsyncClient(
        base_url=settings.service_url,
        timeout=httpx.Timeout(settings.timeout_seconds),
    )
    return LabInferenceClient(http_client)


def _detail(response: httpx.Response) -> str | None:
    """Best-effort detail string from a lab error body.

    Safe to surface to our caller: it describes the caller's own request (a bad
    template variable, an invalid config), not lab internals.
    """
    try:
        payload = response.json()
    except ValueError:
        return None
    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, str):
            return detail
    return None
