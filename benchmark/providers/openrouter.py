from __future__ import annotations

from typing import Any

from benchmark.providers.openai_compatible import OpenAICompatibleAdapter


class OpenRouterAdapter(OpenAICompatibleAdapter):
    def __init__(
        self,
        model: str,
        api_key: str,
        upstream_provider: str,
        *,
        base_url: str = "https://openrouter.ai/api/v1",
        temperature: float = 0,
        reasoning_effort: str = "none",
        allow_fallbacks: bool = False,
        require_parameters: bool = True,
        client: Any | None = None,
    ) -> None:
        super().__init__(
            model,
            base_url,
            api_key=api_key,
            temperature=temperature,
            extra_body={
                "reasoning": {"effort": reasoning_effort},
                "provider": {
                    "order": [upstream_provider],
                    "allow_fallbacks": allow_fallbacks,
                    "require_parameters": require_parameters,
                },
            },
            extra_headers={"X-OpenRouter-Metadata": "enabled"},
            client=client,
        )
