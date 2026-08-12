from __future__ import annotations

from typing import Any

from benchmark.providers.openai_compatible import OpenAICompatibleAdapter


class HuggingFaceNscaleAdapter(OpenAICompatibleAdapter):
    def __init__(
        self,
        model: str,
        api_key: str,
        *,
        base_url: str = "https://router.huggingface.co/v1",
        temperature: float = 0,
        reasoning_effort: str = "none",
        max_retries: int = 5,
        client: Any | None = None,
    ) -> None:
        if not model.endswith(":nscale"):
            raise ValueError("Hugging Face Qwen model must be explicitly pinned with :nscale")
        super().__init__(
            model,
            base_url,
            api_key=api_key,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
            max_retries=max_retries,
            client=client,
        )
