"""OpenAI-compatible judge-model adapter.

One adapter covers OpenAI, Azure OpenAI and **self-hosted** servers that speak
the OpenAI chat-completions API (vLLM, Ollama, LM Studio, TGI, ...). The only
difference is ``base_url`` (and the key), so personal/company models plug in
without new code.
"""

from __future__ import annotations

import httpx

from arc_eval_service.core.errors import ModelError
from arc_eval_service.judging.model import JudgeModel, ModelCompletion, ModelSettings


class OpenAICompatibleModel(JudgeModel):
    """Calls a ``/chat/completions`` endpoint for a single-turn judge completion."""

    provider = "openai_compatible"

    def __init__(
        self,
        *,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        api_key: str | None = None,
        timeout_s: float = 30.0,
    ) -> None:
        self.name = model
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout_s = timeout_s

    async def complete(
        self, *, system: str | None, prompt: str, settings: ModelSettings
    ) -> ModelCompletion:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.name,
            "messages": messages,
            "temperature": settings.temperature,
            "max_tokens": settings.max_tokens,
        }
        headers = {"content-type": "application/json"}
        if self._api_key:
            headers["authorization"] = f"Bearer {self._api_key}"

        try:
            async with httpx.AsyncClient(timeout=self._timeout_s) as client:
                resp = await client.post(
                    f"{self._base_url}/chat/completions", json=payload, headers=headers
                )
                resp.raise_for_status()
                data = resp.json()
            choice = data["choices"][0]["message"]["content"]
        except (httpx.HTTPError, ValueError, KeyError, IndexError) as exc:
            raise ModelError(f"openai-compatible call failed: {exc}") from exc

        usage = data.get("usage", {})
        return ModelCompletion(
            text=choice or "",
            model=data.get("model", self.name),
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
        )
