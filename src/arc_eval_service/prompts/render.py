"""Render a metric's case template with the case's values.

The template uses ``{input}``, ``{output}``, ``{context}`` and ``{reference}``
placeholders. Substitution is literal (no format-string parsing), so text
containing braces is safe. Absent fields render empty; context passages are
numbered.
"""

from __future__ import annotations

from arc_eval_service.evaluation.schemas import EvaluationCase

_SLOTS = ("input", "output", "context", "reference")


def render_case(template: str, case: EvaluationCase) -> str:
    """Fill a metric template's placeholders from the case."""
    values = {
        "input": case.input or "",
        "output": case.output or "",
        "context": _format_context(case.context),
        "reference": case.reference or "",
    }
    rendered = template
    for slot in _SLOTS:
        rendered = rendered.replace("{" + slot + "}", values[slot])
    return rendered


def _format_context(context: list[str] | None) -> str:
    """Number the context passages, or empty string when there are none."""
    if not context:
        return ""
    return "\n".join(
        f"[{index}] {passage.strip()}" for index, passage in enumerate(context, 1)
    )
