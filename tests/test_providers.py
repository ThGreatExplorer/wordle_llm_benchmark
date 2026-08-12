import asyncio
from types import SimpleNamespace as NS

from benchmark.providers import OpenAICompatibleAdapter, OpenAIResponsesAdapter


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
        choices=[NS(message=NS(content='{"guesses":["only"]}'))], model="qwen", _request_id="req",
        usage=NS(prompt_tokens=8, completion_tokens=3, completion_tokens_details=None),
    ))
    client = NS(chat=NS(completions=endpoint))
    result = asyncio.run(OpenAICompatibleAdapter("qwen", "http://localhost/v1", client=client).predict("prompt"))
    assert result.guesses is None and result.protocol_error == "PROTOCOL_ERROR"
    assert endpoint.request["messages"] == [{"role": "user", "content": "prompt"}]
    assert "previous_response_id" not in endpoint.request
