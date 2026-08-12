from __future__ import annotations

import time
from typing import Any

from openai import AsyncOpenAI

from benchmark.providers.mock import parse_top_three
from benchmark.providers.openai_responses import TOP_THREE_SCHEMA
from benchmark.types import ModelResponse


class OpenAICompatibleAdapter:
    def __init__(
        self,
        model: str,
        base_url: str,
        *,
        api_key: str = "not-required",
        temperature: float = 0,
        extra_body: dict[str, Any] | None = None,
        client: Any | None = None,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.extra_body = extra_body
        self.client = client or AsyncOpenAI(
            api_key=api_key, base_url=base_url, max_retries=3, timeout=120.0
        )

    async def predict(self, prompt: str) -> ModelResponse:
        request: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "top_three_guesses", "strict": True, "schema": TOP_THREE_SCHEMA},
            },
        }
        if self.extra_body:
            request["extra_body"] = self.extra_body
        started = time.perf_counter()
        response = await self.client.chat.completions.create(**request)
        latency = (time.perf_counter() - started) * 1000
        raw = response.choices[0].message.content or ""
        guesses = parse_top_three(raw)
        usage = getattr(response, "usage", None)
        details = getattr(usage, "completion_tokens_details", None)
        return ModelResponse(
            raw_text=raw,
            guesses=guesses,
            input_tokens=getattr(usage, "prompt_tokens", None),
            output_tokens=getattr(usage, "completion_tokens", None),
            reasoning_tokens=getattr(details, "reasoning_tokens", None),
            latency_ms=latency,
            provider_request_id=getattr(response, "_request_id", None),
            model_returned=getattr(response, "model", None),
            provider_returned=getattr(response, "provider", None),
            protocol_error=None if guesses is not None else "PROTOCOL_ERROR",
        )
