import asyncio
import json
import pytest

from benchmark.experiment.batch import run_batch
from benchmark.types import Condition, GameState, ModelResponse


class SolvingAdapter:
    active = 0
    maximum = 0

    async def predict(self, prompt: str) -> ModelResponse:
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
