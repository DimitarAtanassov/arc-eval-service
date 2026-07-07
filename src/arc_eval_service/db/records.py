"""Persistence domain models: what the service hands to the repositories.

These sit between the wire contract (:mod:`arc_eval_service.api.schemas`) and the
ORM rows (:mod:`arc_eval_service.db.models`). The service builds them; the
repositories map them to rows. Keeping them separate from the wire DTOs means the
storage shape can evolve without changing the public API (and vice versa). ``id``
and timestamps are assigned by the service and database, not the caller.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class NewEvalRequest(BaseModel):
    """An interaction to persist before scoring."""

    id: str
    input_text: str
    output_text: str
    prompt: str | None
    inference_id: str | None
    model_id: str | None
    request_metadata: dict[str, Any]


class NewEvaluationResult(BaseModel):
    """One metric score to persist (successful or errored)."""

    id: str
    eval_request_id: str
    inference_id: str | None
    model_id: str | None
    metric_name: str
    score: float
    passed: bool
    reasoning: str | None
    evaluator_name: str
    evaluator_version: str | None
    judge: dict[str, Any] | None
    prompt: dict[str, Any] | None
    latency_ms: float
    error: str | None


class StoredEvalRequest(BaseModel):
    """A persisted eval request read back from storage (row shape, id + timestamp)."""

    id: str
    input_text: str
    output_text: str
    prompt: str | None
    inference_id: str | None
    model_id: str | None
    request_metadata: dict[str, Any]
    created_at: datetime


class StoredEvaluationResult(BaseModel):
    """A persisted metric score read back from storage (row shape, id + timestamp)."""

    id: str
    eval_request_id: str
    inference_id: str | None
    model_id: str | None
    metric_name: str
    score: float
    passed: bool
    reasoning: str | None
    evaluator_name: str
    evaluator_version: str | None
    judge: dict[str, Any] | None
    prompt: dict[str, Any] | None
    latency_ms: float
    error: str | None
    created_at: datetime
