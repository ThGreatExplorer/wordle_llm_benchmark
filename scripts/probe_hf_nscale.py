from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from benchmark.providers.mock import parse_top_three
from benchmark.providers.openai_responses import TOP_THREE_SCHEMA
from benchmark.experiment.manifests import load_game_states, load_words
from benchmark.prompts import build_prompt
from benchmark.types import Condition

BASE_URL = "https://router.huggingface.co/v1"
MODELS = (
    "Qwen/Qwen3-8B:nscale",
    "Qwen/Qwen3-14B:nscale",
    "Qwen/Qwen3-32B:nscale",
)
PROMPT = 'Return exactly this JSON object with any three strings: {"guesses":["one","two","three"]}'
SCHEMA_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "top_three_guesses",
        "strict": True,
        "schema": TOP_THREE_SCHEMA,
    },
}


def request_for(
    model: str, stage: str = "full", prompt: str = PROMPT, max_tokens: int = 128,
) -> dict[str, Any]:
    request: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
    }
    if stage in {"temperature", "reasoning", "schema", "full"}:
        request["temperature"] = 0
    if stage in {"reasoning", "schema", "full"}:
        request["reasoning_effort"] = "none"
    if stage in {"schema", "full"}:
        request["response_format"] = SCHEMA_FORMAT
    return request


def _error(exc: Exception) -> dict[str, Any]:
    return {
        "ok": False,
        "error_type": type(exc).__name__,
        "status_code": getattr(exc, "status_code", None),
        "message": str(exc),
    }


async def attempt(
    client: Any, model: str, stage: str, prompt: str = PROMPT, max_tokens: int = 128,
) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        response = await client.chat.completions.create(**request_for(model, stage, prompt, max_tokens))
    except Exception as exc:
        return {"stage": stage, "latency_ms": (time.perf_counter() - started) * 1000, **_error(exc)}

    raw = response.choices[0].message.content or ""
    usage = getattr(response, "usage", None)
    details = getattr(usage, "completion_tokens_details", None)
    guesses = parse_top_three(raw)
    return {
        "stage": stage,
        "ok": guesses is not None if stage in {"schema", "full"} else True,
        "requested_model": model,
        "max_tokens": max_tokens,
        "returned_model": getattr(response, "model", None),
        "request_id": getattr(response, "_request_id", None),
        "input_tokens": getattr(usage, "prompt_tokens", None),
        "output_tokens": getattr(usage, "completion_tokens", None),
        "reasoning_tokens": getattr(details, "reasoning_tokens", None),
        "latency_ms": (time.perf_counter() - started) * 1000,
        "raw_response": raw,
        "guesses": guesses,
        "protocol_error": None if guesses is not None else "PROTOCOL_ERROR",
    }


async def probe_model(
    client: Any, model: str, prompt: str = PROMPT, max_tokens: int = 128,
) -> dict[str, Any]:
    full = await attempt(client, model, "full", prompt, max_tokens)
    if full["ok"]:
        return {"model": model, "passed": True, "attempts": [full]}
    if full.get("status_code") is None and full.get("protocol_error"):
        return {"model": model, "passed": False, "attempts": [full]}

    attempts = [full]
    for stage in ("basic", "temperature", "reasoning", "schema"):
        result = await attempt(client, model, stage, prompt, max_tokens)
        attempts.append(result)
        if not result["ok"]:
            break
    return {"model": model, "passed": attempts[-1]["ok"], "attempts": attempts}


async def run(
    models: tuple[str, ...], token: str, prompt: str = PROMPT, max_tokens: int = 128,
) -> list[dict[str, Any]]:
    client = AsyncOpenAI(base_url=BASE_URL, api_key=token, max_retries=0, timeout=120.0)
    return [await probe_model(client, model, prompt, max_tokens) for model in models]


def dynamic_prompt() -> str:
    state = load_game_states(
        Path("data/manifests/dev_dynamic.jsonl"),
        Condition.DYNAMIC_256,
        load_words(Path("data/frozen/wordle_answers_2022.txt")),
        load_words(Path("data/frozen/wordle_extra_guesses_2022.txt")),
    )[0][1]
    return build_prompt(Condition.DYNAMIC_256, state, 1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe the frozen HF/Nscale Qwen request contract")
    parser.add_argument("--model", action="append", choices=MODELS, dest="models")
    parser.add_argument("--dynamic-prompt", action="store_true")
    parser.add_argument("--max-tokens", type=int, default=128)
    args = parser.parse_args()
    token = os.environ.get("HF_TOKEN")
    if not token:
        raise SystemExit("HF_TOKEN is required")
    results = asyncio.run(run(
        tuple(args.models or MODELS), token, dynamic_prompt() if args.dynamic_prompt else PROMPT,
        args.max_tokens,
    ))
    print(json.dumps(results, indent=2))
    raise SystemExit(0 if all(result["passed"] for result in results) else 1)


if __name__ == "__main__":
    main()
