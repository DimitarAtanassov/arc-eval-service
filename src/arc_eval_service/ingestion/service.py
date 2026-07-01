"""Ingestion orchestration: store the eval input.

This is the whole job of the endpoint: it records one LLM interaction. It runs no
evaluation; the ``metrics`` and ``evaluation_runs`` tables are written by the
evaluation logic, not here.
"""

from __future__ import annotations

from uuid import uuid4

from arc_eval_service.db.repositories import EvalInputRepository
from arc_eval_service.ingestion.schemas import (
    EvalInputRequest,
    EvalInputResponse,
    NewEvalInput,
)


class IngestionService:
    """Stores one LLM interaction as an eval input."""

    def __init__(self, *, inputs: EvalInputRepository) -> None:
        self._inputs = inputs

    async def record(self, request: EvalInputRequest) -> EvalInputResponse:
        """Store the eval input and return its id."""
        new_input = NewEvalInput(
            id=str(uuid4()),
            rendered_prompt=request.rendered_prompt,
            system_message=request.system_message,
            response=request.response,
            config=request.config,
        )
        await self._inputs.create(new_input)
        return EvalInputResponse(eval_input_id=new_input.id)
