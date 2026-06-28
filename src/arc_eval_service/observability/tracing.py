"""OpenTelemetry tracing setup.

MVP design: console exporter ONLY. The service layer creates one root span per
evaluation request and one child span per evaluator (see
:mod:`arc_eval_service.services.evaluation`). This module owns the
provider/exporter wiring and exposes a single tracer accessor.
"""

from __future__ import annotations

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor
from opentelemetry.trace import Tracer

TRACER_NAME = "arc.eval"

_CONFIGURED = False


def setup_tracing(service_name: str = "arc-eval-service") -> None:
    """Configure the global tracer provider with a console exporter.

    Idempotent: calling more than once is a no-op so app startup and tests can
    safely invoke it repeatedly without stacking exporters.
    """
    global _CONFIGURED  # noqa: PLW0603 - module-level singleton guard
    if _CONFIGURED:
        return

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
    _CONFIGURED = True


def get_tracer() -> Tracer:
    """Return the tracer used across the evaluation service."""
    return trace.get_tracer(TRACER_NAME)
