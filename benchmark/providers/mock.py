from __future__ import annotations

import json
from collections.abc import Iterable

from benchmark.types import ModelResponse


def parse_top_three(raw_text: str) -> list[str] | None:
    try:
        payload = json.loads(raw_text)
    except (json.JSONDecodeError, TypeError):
        return None
    guesses = payload.get("guesses") if isinstance(payload, dict) else None
    return guesses if isinstance(guesses, list) and len(guesses) == 3 and all(isinstance(x, str) for x in guesses) else None


class MockAdapter:
    def __init__(self, responses: Iterable[str | list[str]]) -> None:
        self._responses = iter(responses)
        self.prompts: list[str] = []

    async def predict(self, prompt: str) -> ModelResponse:
        self.prompts.append(prompt)
        response = next(self._responses)
        raw = response if isinstance(response, str) else json.dumps({"guesses": response})
        guesses = parse_top_three(raw)
        return ModelResponse(raw_text=raw, guesses=guesses, protocol_error=None if guesses else "PROTOCOL_ERROR")
