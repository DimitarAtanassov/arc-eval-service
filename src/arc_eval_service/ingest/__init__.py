"""OTel offline ingestion (inbound adapter): gateway -> collector -> evaluator.

Three modules, one per reason to change: :mod:`wire` (OTLP/HTTP schema),
:mod:`mapping` (pure span -> domain functions), and :mod:`service` (the
imperative shell). This package is the stable public surface.
"""

from __future__ import annotations

from arc_eval_service.ingest.mapping import parse_spans, spans_to_cases
from arc_eval_service.ingest.service import OfflineIngestService
from arc_eval_service.ingest.wire import OTLPTracePayload

__all__ = [
    "OTLPTracePayload",
    "OfflineIngestService",
    "parse_spans",
    "spans_to_cases",
]
