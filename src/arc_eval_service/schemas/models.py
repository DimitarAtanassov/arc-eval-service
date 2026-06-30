"""Domain model aggregator (stable import surface).

Models are organised by domain in sibling modules (:mod:`evaluation`,
:mod:`trace`, :mod:`discovery`). This module re-exports them so
``arc_eval_service.schemas.models`` stays the single, stable import path used
across the service and its tests.
"""

from __future__ import annotations

from arc_eval_service.schemas.discovery import JudgeInfo, ModelProfileInfo
from arc_eval_service.schemas.evaluation import (
    ConfigValue,
    EvaluationCase,
    EvaluationRecord,
    EvaluationRequest,
    EvaluationResult,
    EvaluationStatus,
    ExecutionMode,
    JudgeSpec,
)
from arc_eval_service.schemas.trace import Span, SpanRecord, Trace

__all__ = [
    "ConfigValue",
    "EvaluationCase",
    "EvaluationRecord",
    "EvaluationRequest",
    "EvaluationResult",
    "EvaluationStatus",
    "ExecutionMode",
    "JudgeInfo",
    "JudgeSpec",
    "ModelProfileInfo",
    "Span",
    "SpanRecord",
    "Trace",
]
