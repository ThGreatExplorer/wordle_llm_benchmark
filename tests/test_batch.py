import asyncio
import json

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
