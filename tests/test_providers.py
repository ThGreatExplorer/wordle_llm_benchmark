import asyncio
from types import SimpleNamespace as NS

from benchmark.providers import OpenAICompatibleAdapter, OpenAIResponsesAdapter, OpenRouterAdapter


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


def test_openrouter_adapter_pins_upstream_and_disables_reasoning_and_fallbacks() -> None:
    endpoint = Capture(NS(
        choices=[NS(message=NS(content='{"guesses":["crane","slate","trace"]}'))],
        model="qwen/qwen3-14b", provider="DeepInfra", _request_id="req",
        usage=NS(prompt_tokens=8, completion_tokens=3, completion_tokens_details=None),
    ))
    result = asyncio.run(OpenRouterAdapter(
        "qwen/qwen3-14b", "key", "deepinfra", client=NS(chat=NS(completions=endpoint))
    ).predict("prompt"))
    assert endpoint.request["extra_body"] == {
        "reasoning": {"effort": "none"},
        "provider": {"order": ["deepinfra"], "allow_fallbacks": False, "require_parameters": True},
    }
    assert endpoint.request["extra_headers"] == {"X-OpenRouter-Metadata": "enabled"}
    assert result.model_returned == "qwen/qwen3-14b"
    assert result.provider_returned == "DeepInfra"


def test_openrouter_reads_provider_from_sdk_extra_metadata() -> None:
    endpoint = Capture(NS(
        choices=[NS(message=NS(content='{"guesses":["crane","slate","trace"]}'))],
        model="qwen/qwen3-8b", model_extra={
            "openrouter_metadata": {"attempts": [{"provider": "Alibaba", "model": "qwen/qwen3-8b:actual", "status": 200}]},
        }, _request_id="req", usage=None,
    ))
    result = asyncio.run(OpenRouterAdapter(
        "qwen/qwen3-8b", "key", "alibaba", client=NS(chat=NS(completions=endpoint))
    ).predict("prompt"))
    assert result.provider_returned == "Alibaba"
    assert result.model_returned == "qwen/qwen3-8b:actual"
    assert result.provider_metadata["attempts"][0]["status"] == 200
