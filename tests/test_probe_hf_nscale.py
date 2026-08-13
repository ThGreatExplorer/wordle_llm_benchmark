import asyncio
from types import SimpleNamespace as NS

from scripts.probe_hf_nscale import MODELS, SCHEMA_FORMAT, dynamic_prompt, probe_model, request_for


class Endpoint:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    async def create(self, **request):
        self.requests.append(request)
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


def response(content='{"guesses":["one","two","three"]}'):
    return NS(
        choices=[NS(message=NS(content=content))], model="returned", _request_id="req",
        usage=NS(prompt_tokens=4, completion_tokens=5, completion_tokens_details=NS(reasoning_tokens=0)),
    )


def test_full_probe_uses_exact_pinned_contract() -> None:
    endpoint = Endpoint([response()])
    result = asyncio.run(probe_model(NS(chat=NS(completions=endpoint)), MODELS[0]))
    assert result["passed"] and len(endpoint.requests) == 1
    assert endpoint.requests[0] == {
        "model": "Qwen/Qwen3-8B:nscale",
        "messages": [{"role": "user", "content": request_for(MODELS[0])["messages"][0]["content"]}],
        "temperature": 0,
        "max_tokens": 128,
        "reasoning_effort": "none",
        "response_format": SCHEMA_FORMAT,
    }
    assert result["attempts"][0]["reasoning_tokens"] == 0


def test_failed_full_probe_isolates_first_unsupported_feature() -> None:
    endpoint = Endpoint([RuntimeError("full"), response("plain"), response("plain"), RuntimeError("reasoning")])
    result = asyncio.run(probe_model(NS(chat=NS(completions=endpoint)), MODELS[1]))
    assert not result["passed"]
    assert [attempt["stage"] for attempt in result["attempts"]] == [
        "full", "basic", "temperature", "reasoning"
    ]
    assert "temperature" not in endpoint.requests[1]
    assert endpoint.requests[2]["temperature"] == 0
    assert endpoint.requests[3]["reasoning_effort"] == "none"


def test_schema_success_requires_exactly_three_strings() -> None:
    endpoint = Endpoint([response('{"guesses":["only"]}')])
    result = asyncio.run(probe_model(NS(chat=NS(completions=endpoint)), MODELS[2]))
    assert not result["passed"]
    assert result["attempts"][0]["protocol_error"] == "PROTOCOL_ERROR"


def test_dynamic_probe_uses_exact_frozen_first_round_prompt() -> None:
    prompt = dynamic_prompt()
    assert "Candidate words, in fixed order:" in prompt
    assert len(prompt) > 2_000
    assert request_for(MODELS[0], prompt=prompt)["messages"] == [
        {"role": "user", "content": prompt}
    ]
