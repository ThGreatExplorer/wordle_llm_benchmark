from __future__ import annotations

import time
from typing import Any

from openai import AsyncOpenAI

from benchmark.providers.mock import parse_top_three
from benchmark.providers.openai_responses import TOP_THREE_SCHEMA
from benchmark.types import ModelResponse


def _response_field(response: Any, name: str) -> Any:
    value = getattr(response, name, None)
    if value is not None:
        return value
    return (getattr(response, "model_extra", None) or {}).get(name)


def _routed_field(metadata: Any, name: str) -> Any:
    if not isinstance(metadata, dict):
        return None
    attempts = metadata.get("attempts") or []
    return attempts[-1].get(name) if attempts and isinstance(attempts[-1], dict) else None


class OpenAICompatibleAdapter:
    def __init__(
        self,
        model: str,
        base_url: str,
        *,
        api_key: str = "not-required",
        temperature: float = 0,
        reasoning_effort: str | None = None,
        max_retries: int = 3,
        extra_body: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
        client: Any | None = None,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.reasoning_effort = reasoning_effort
        self.extra_body = extra_body
        self.extra_headers = extra_headers
        self.client = client or AsyncOpenAI(
            api_key=api_key, base_url=base_url, max_retries=max_retries, timeout=120.0
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
        if self.reasoning_effort is not None:
            request["reasoning_effort"] = self.reasoning_effort
        if self.extra_body:
            request["extra_body"] = self.extra_body
        if self.extra_headers:
            request["extra_headers"] = self.extra_headers
        started = time.perf_counter()
        response = await self.client.chat.completions.create(**request)
        latency = (time.perf_counter() - started) * 1000
        raw = response.choices[0].message.content or ""
        guesses = parse_top_three(raw)
        usage = getattr(response, "usage", None)
        details = getattr(usage, "completion_tokens_details", None)
        provider_metadata = _response_field(response, "openrouter_metadata")
        return ModelResponse(
            raw_text=raw,
            guesses=guesses,
            input_tokens=getattr(usage, "prompt_tokens", None),
            output_tokens=getattr(usage, "completion_tokens", None),
            reasoning_tokens=getattr(details, "reasoning_tokens", None),
            latency_ms=latency,
            provider_request_id=getattr(response, "_request_id", None),
            model_returned=_routed_field(provider_metadata, "model") or _response_field(response, "model"),
            provider_returned=_routed_field(provider_metadata, "provider") or _response_field(response, "provider"),
            provider_metadata=provider_metadata,
            protocol_error=None if guesses is not None else "PROTOCOL_ERROR",
        )
