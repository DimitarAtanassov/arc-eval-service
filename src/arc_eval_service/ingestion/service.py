"""Ingestion orchestration: store the prompt template and the eval input.

This is the whole job of the endpoint. It deduplicates the prompt template, then
records the interaction. It runs no evaluation; the ``metrics`` and
``evaluation_runs`` tables are written by the evaluation logic, not here.
"""

from __future__ import annotations

from uuid import uuid4

from arc_eval_service.db.repositories import (
    EvalInputRepository,
    PromptTemplateRepository,
)
from arc_eval_service.ingestion.schemas import (
    EvalInputRequest,
    EvalInputResponse,
    NewEvalInput,
)


class IngestionService:
    """Stores one LLM interaction: its prompt template and the eval input."""

    def __init__(
        self,
        *,
        templates: PromptTemplateRepository,
        inputs: EvalInputRepository,
    ) -> None:
        self._templates = templates
        self._inputs = inputs

    async def record(self, request: EvalInputRequest) -> EvalInputResponse:
        """Store the template (deduplicated) and the eval input, return their ids."""
        template_id = await self._templates.get_or_create(request.prompt_template)
        new_input = NewEvalInput(
            id=str(uuid4()),
            prompt_template_id=template_id,
            template_context=request.template_context,
            rendered_prompt=request.rendered_prompt,
            system_message=request.system_message,
            llm_response=request.llm_response,
            llm_config=request.llm_config,
        )
        await self._inputs.create(new_input)
        return EvalInputResponse(
            eval_input_id=new_input.id, prompt_template_id=template_id
        )
