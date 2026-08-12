from __future__ import annotations

import time
from typing import Any

from openai import AsyncOpenAI

from benchmark.providers.mock import parse_top_three
from benchmark.types import ModelResponse

TOP_THREE_SCHEMA = {
    "type": "object",
    "properties": {
        "guesses": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 3,
            "maxItems": 3,
        }
    },
    "required": ["guesses"],
    "additionalProperties": False,
}


class OpenAIResponsesAdapter:
    def __init__(
        self,
        model: str,
        *,
        reasoning_effort: str | None = None,
        temperature: float | None = None,
        client: Any | None = None,
    ) -> None:
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.temperature = temperature
        self.client = client or AsyncOpenAI(max_retries=3, timeout=120.0)

    async def predict(self, prompt: str) -> ModelResponse:
        request: dict[str, Any] = {
            "model": self.model,
            "input": prompt,
            "store": False,
            "text": {"format": {"type": "json_schema", "name": "top_three_guesses", "strict": True,
                                "schema": TOP_THREE_SCHEMA}},
        }
        if self.reasoning_effort is not None:
            request["reasoning"] = {"effort": self.reasoning_effort}
        if self.temperature is not None:
            request["temperature"] = self.temperature

        started = time.perf_counter()
        response = await self.client.responses.create(**request)
        latency = (time.perf_counter() - started) * 1000
        raw = response.output_text
        guesses = parse_top_three(raw)
        usage = getattr(response, "usage", None)
        details = getattr(usage, "output_tokens_details", None)
        return ModelResponse(
            raw_text=raw,
            guesses=guesses,
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
            reasoning_tokens=getattr(details, "reasoning_tokens", None),
            latency_ms=latency,
            provider_request_id=getattr(response, "_request_id", None),
            model_returned=getattr(response, "model", None),
            protocol_error=None if guesses is not None else "PROTOCOL_ERROR",
        )
