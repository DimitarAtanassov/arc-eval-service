"""Discovery DTOs: read-only metadata about registered metrics and models.

These never carry secrets; they describe *what* can be evaluated and on which
model profiles, for the control plane's discovery surfaces.
"""

from __future__ import annotations

from pydantic import BaseModel


class MetricInfo(BaseModel):
    """Discovery metadata for a registered metric."""

    name: str
    description: str
    requires: list[str]


class ModelProfileInfo(BaseModel):
    """Discovery metadata for a configured model profile (no secrets)."""

    name: str
    provider: str
    model: str
    base_url: str | None = None
