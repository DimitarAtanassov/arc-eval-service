"""Anthropic (Claude) judge-model adapter."""

from __future__ import annotations

import httpx

from arc_eval_service.core.errors import ModelError
from arc_eval_service.judging.model import JudgeModel, ModelCompletion, ModelSettings

_API_VERSION = "2023-06-01"


class AnthropicModel(JudgeModel):
    """Calls the Anthropic Messages API for a single-turn judge completion."""

    provider = "anthropic"

    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        base_url: str = "https://api.anthropic.com",
        timeout_s: float = 30.0,
    ) -> None:
        self.name = model
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s

    async def complete(
        self, *, system: str | None, prompt: str, settings: ModelSettings
    ) -> ModelCompletion:
        payload: dict[str, object] = {
            "model": self.name,
            "max_tokens": settings.max_tokens,
            "temperature": settings.temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            payload["system"] = system
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": _API_VERSION,
            "content-type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout_s) as client:
                resp = await client.post(
                    f"{self._base_url}/v1/messages", json=payload, headers=headers
                )
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ModelError(f"anthropic call failed: {exc}") from exc

        text = "".join(
            block.get("text", "")
            for block in data.get("content", [])
            if block.get("type") == "text"
        )
        usage = data.get("usage", {})
        return ModelCompletion(
            text=text,
            model=data.get("model", self.name),
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
        )
