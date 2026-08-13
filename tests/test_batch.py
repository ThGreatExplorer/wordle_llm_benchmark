import asyncio
import json
import pytest

from benchmark.experiment.batch import clean_partial_proposals, completed_game_ids, run_batch
from benchmark.providers.openai_responses import RequestTimeoutError
from benchmark.types import Condition, GameMode, GameState, ModelResponse


class SolvingAdapter:
    active = 0
    maximum = 0

    def __init__(self) -> None:
        self.calls = 0

    async def predict(self, prompt: str) -> ModelResponse:
        self.calls += 1
        self.active += 1
        self.maximum = max(self.maximum, self.active)
        await asyncio.sleep(0)
        self.active -= 1
        return ModelResponse(
            raw_text='{"guesses":["slate","crane","trace"]}',
            guesses=["slate", "crane", "trace"], input_tokens=10, output_tokens=5,
        )


def test_batch_is_bounded_resumable_and_costed(tmp_path) -> None:
    adapter = SolvingAdapter()
    games = [
        (f"game-{index}", GameState("slate", ("slate", "crane", "trace"), ("slate", "crane", "trace")))
        for index in range(3)
    ]
    proposals, summaries = tmp_path / "proposals.jsonl", tmp_path / "summaries.jsonl"
    results = asyncio.run(run_batch(
        adapter, Condition.HIST_NAMED, games, proposals, summaries,
        run_id="run", model_key="model", concurrency=2, prices=(1, 2, 0),
    ))
    assert len(results) == 3 and adapter.maximum == 2
    rows = [json.loads(line) for line in summaries.read_text().splitlines()]
    assert len(rows) == 3 and rows[0]["estimated_cost_usd_total"] == 20 / 1_000_000
    resumed = asyncio.run(run_batch(
        adapter, Condition.HIST_NAMED, games, proposals, summaries,
        run_id="run", model_key="model", concurrency=2,
    ))
    assert resumed == () and len(summaries.read_text().splitlines()) == 3


def test_unknown_pricing_is_null_and_rejects_cost_guard(tmp_path) -> None:
    game = ("game", GameState("slate", ("slate",), ("slate", "crane", "trace")))
    proposals, summaries = tmp_path / "proposals.jsonl", tmp_path / "summaries.jsonl"
    result = asyncio.run(run_batch(
        SolvingAdapter(), Condition.HIST_NAMED, [game], proposals, summaries,
        run_id="run", model_key="model", prices=(None, None, 0),
    ))
    assert result[0].summary.estimated_cost_usd_total is None
    with pytest.raises(ValueError, match="requires configured model pricing"):
        asyncio.run(run_batch(
            SolvingAdapter(), Condition.HIST_NAMED, [game], proposals, summaries,
            run_id="other", model_key="model", prices=(None, None, 0), max_cost_usd=1,
        ))


def test_duplicate_summary_fails_and_completed_run_makes_no_calls(tmp_path) -> None:
    game = ("game", GameState("slate", ("slate",), ("slate", "crane", "trace")))
    proposals, summaries = tmp_path / "proposals.jsonl", tmp_path / "summaries.jsonl"
    first = SolvingAdapter()
    asyncio.run(run_batch(first, Condition.HIST_NAMED, [game], proposals, summaries,
                          run_id="run", model_key="model"))
    resumed = SolvingAdapter()
    assert asyncio.run(run_batch(resumed, Condition.HIST_NAMED, [game], proposals, summaries,
                                 run_id="run", model_key="model")) == ()
    assert resumed.calls == 0
    summaries.write_text(summaries.read_text() * 2)
    with pytest.raises(ValueError, match="duplicate completed summary"):
        completed_game_ids(summaries, "run", "model", Condition.HIST_NAMED, GameMode.NORMAL)


def test_orphan_proposals_are_cleaned_and_game_reruns(tmp_path) -> None:
    proposals, summaries = tmp_path / "proposals.jsonl", tmp_path / "summaries.jsonl"
    orphan = {"run_id": "run", "model_key": "model", "condition": "hist_named",
              "game_mode": "normal", "game_id": "game", "proposal_type": "initial"}
    proposals.write_text(json.dumps(orphan) + "\n")
    assert clean_partial_proposals(proposals, summaries) == (1, 1)
    assert proposals.read_text() == ""
    adapter = SolvingAdapter()
    game = ("game", GameState("slate", ("slate",), ("slate", "crane", "trace")))
    result = asyncio.run(run_batch(adapter, Condition.HIST_NAMED, [game], proposals, summaries,
                                   run_id="run", model_key="model"))
    assert len(result) == adapter.calls == 1


def test_request_timeout_is_infrastructure_and_game_remains_incomplete(tmp_path) -> None:
    class TimedOut:
        async def predict(self, prompt: str) -> ModelResponse:
            raise RequestTimeoutError("REQUEST_TIMEOUT")

    game = ("game", GameState("slate", ("slate",), ("slate", "crane", "trace")))
    proposals, summaries = tmp_path / "proposals.jsonl", tmp_path / "summaries.jsonl"
    with pytest.raises(RequestTimeoutError):
        asyncio.run(run_batch(
            TimedOut(), Condition.HIST_NAMED, [game], proposals, summaries,
            run_id="run", model_key="gpt5_medium",
        ))
    assert not summaries.exists()
    event = json.loads((tmp_path / "infrastructure.jsonl").read_text())
    assert event["error"] == "REQUEST_TIMEOUT" and event["game_id"] == "game"


def test_resume_progress_and_existing_cost_guard(tmp_path, capsys) -> None:
    games = [(f"g{i}", GameState("slate", ("slate",), ("slate", "crane", "trace"))) for i in range(2)]
    proposals, summaries = tmp_path / "proposals.jsonl", tmp_path / "summaries.jsonl"
    asyncio.run(run_batch(SolvingAdapter(), Condition.HIST_NAMED, games[:1], proposals, summaries,
                          run_id="run", model_key="model", prices=(1_000_000, 0, 0)))
    adapter = SolvingAdapter()
    asyncio.run(run_batch(adapter, Condition.HIST_NAMED, games, proposals, summaries,
                          run_id="run", model_key="model", prices=(1_000_000, 0, 0),
                          max_cost_usd=1))
    output = capsys.readouterr().out
    assert "Cost guard reached." in output and "Completed: 1/2" in output
    assert adapter.calls == 0
