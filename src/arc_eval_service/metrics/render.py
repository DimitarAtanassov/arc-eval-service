"""Shared case-rendering helpers for built-in metrics (DRY)."""

from __future__ import annotations

from arc_eval_service.evaluation.schemas import EvaluationCase


def section(label: str, value: str | None) -> str:
    """Render a labelled section, or empty string when the value is absent."""
    return f"### {label}\n{value.strip()}\n" if value else ""


def context_block(case: EvaluationCase) -> str:
    """Render the context passages as a single labelled, numbered block."""
    if not case.context:
        return ""
    joined = "\n".join(f"[{i}] {c.strip()}" for i, c in enumerate(case.context, 1))
    return f"### Context\n{joined}\n"
