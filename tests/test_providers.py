import asyncio
from types import SimpleNamespace as NS

import pytest

from benchmark.providers import (
    HuggingFaceNscaleAdapter, OpenAICompatibleAdapter, OpenAIResponsesAdapter,
)
from benchmark.providers.openai_responses import TOP_THREE_SCHEMA
from scripts.probe_hf_nscale import request_for


class Capture:
    def __init__(self, response):
        self.response = response
        self.request = None

    async def create(self, **request):
        self.request = request
        return self.response


def test_responses_adapter_is_stateless_and_captures_usage() -> None:
    endpoint = Capture(NS(
        output_text='{"guesses":["crane","slate","trace"]}', model="returned", _request_id="req",
        usage=NS(input_tokens=10, output_tokens=5, output_tokens_details=NS(reasoning_tokens=2)),
    ))
    result = asyncio.run(OpenAIResponsesAdapter(
        "requested", reasoning_effort="none", client=NS(responses=endpoint)
    ).predict("prompt"))
    assert result.guesses == ["crane", "slate", "trace"]
    assert (result.input_tokens, result.output_tokens, result.reasoning_tokens) == (10, 5, 2)
    assert endpoint.request["store"] is False
    assert "previous_response_id" not in endpoint.request and endpoint.request["input"] == "prompt"


def test_compatible_adapter_is_stateless_and_preserves_protocol_errors() -> None:
    endpoint = Capture(NS(
        choices=[NS(message=NS(content='{"guesses":["only"]}'))], model="qwen", provider="openrouter-provider", _request_id="req",
        usage=NS(prompt_tokens=8, completion_tokens=3, completion_tokens_details=None),
    ))
    client = NS(chat=NS(completions=endpoint))
    result = asyncio.run(OpenAICompatibleAdapter(
        "qwen", "https://openrouter.ai/api/v1", extra_body={"reasoning": {"effort": "none"}}, client=client
    ).predict("prompt"))
    assert result.guesses is None and result.protocol_error == "PROTOCOL_ERROR"
    assert result.provider_returned == "openrouter-provider"
    assert endpoint.request["messages"] == [{"role": "user", "content": "prompt"}]
    assert endpoint.request["extra_body"] == {"reasoning": {"effort": "none"}}
    assert "previous_response_id" not in endpoint.request


def test_huggingface_nscale_adapter_uses_pinned_stateless_contract() -> None:
    endpoint = Capture(NS(
        choices=[NS(message=NS(content='{"guesses":["crane","slate","trace"]}'))],
        model="Qwen/Qwen3-8B", _request_id="req",
        usage=NS(prompt_tokens=8, completion_tokens=3, completion_tokens_details=NS(reasoning_tokens=0)),
    ))
    result = asyncio.run(HuggingFaceNscaleAdapter(
        "Qwen/Qwen3-8B:nscale", "key", client=NS(chat=NS(completions=endpoint))
    ).predict("prompt"))
    assert endpoint.request["model"] == "Qwen/Qwen3-8B:nscale"
    assert endpoint.request["messages"] == [{"role": "user", "content": "prompt"}]
    assert endpoint.request["temperature"] == 0
    assert endpoint.request["reasoning_effort"] == "none"
    assert endpoint.request["response_format"]["json_schema"]["schema"] == TOP_THREE_SCHEMA
    assert "previous_response_id" not in endpoint.request
    assert result.raw_text == '{"guesses":["crane","slate","trace"]}'
    assert result.model_returned == "Qwen/Qwen3-8B" and result.reasoning_tokens == 0


def test_huggingface_nscale_adapter_rejects_unpinned_model() -> None:
    with pytest.raises(ValueError, match=":nscale"):
        HuggingFaceNscaleAdapter("Qwen/Qwen3-8B", "key", client=object())


def test_huggingface_nscale_adapter_preserves_malformed_output() -> None:
    endpoint = Capture(NS(
        choices=[NS(message=NS(content="not json"))], model="Qwen/Qwen3-8B",
        _request_id="req", usage=None,
    ))
    result = asyncio.run(HuggingFaceNscaleAdapter(
        "Qwen/Qwen3-8B:nscale", "key", client=NS(chat=NS(completions=endpoint))
    ).predict("prompt"))
    assert result.raw_text == "not json"
    assert result.guesses is None and result.protocol_error == "PROTOCOL_ERROR"


def test_huggingface_nscale_adapter_configures_bounded_sdk_retries(monkeypatch) -> None:
    captured = {}

    def client(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr("benchmark.providers.openai_compatible.AsyncOpenAI", client)
    HuggingFaceNscaleAdapter("Qwen/Qwen3-8B:nscale", "key")
    assert captured == {
        "api_key": "key", "base_url": "https://router.huggingface.co/v1",
        "max_retries": 5, "timeout": 120.0,
    }


def test_hf_probe_caps_generation_under_exact_contract() -> None:
    request = request_for("Qwen/Qwen3-8B:nscale")
    assert request["max_tokens"] == 128
    assert request["reasoning_effort"] == "none"
    assert request["temperature"] == 0
    assert request["response_format"]["json_schema"]["strict"] is True
