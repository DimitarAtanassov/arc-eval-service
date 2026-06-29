"""OTel offline ingestion (inbound adapter): gateway -> collector -> evaluator."""

from __future__ import annotations

from arc_eval_service.ingest.otlp import (
    OfflineIngestService,
    OTLPTracePayload,
    spans_to_cases,
)

__all__ = ["OTLPTracePayload", "OfflineIngestService", "spans_to_cases"]
