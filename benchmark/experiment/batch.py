from __future__ import annotations

import asyncio
import json
from collections.abc import Iterable
from pathlib import Path

from benchmark.experiment.runner import GameResult, append_result, run_game
from benchmark.types import Condition, GameMode, GameState, ModelAdapter


def completed_game_ids(
    summary_path: Path, run_id: str, model_key: str, condition: Condition, game_mode: GameMode,
) -> set[str]:
    if not summary_path.exists():
        return set()
    completed = set()
    for line in summary_path.read_text().splitlines():
        row = json.loads(line)
        if (row.get("run_id"), row.get("model_key"), row.get("condition"), row.get("game_mode")) == (
            run_id, model_key, condition.value, game_mode.value,
        ):
            completed.add(row["game_id"])
    return completed


def existing_cost(
    summary_path: Path, run_id: str, model_key: str, condition: Condition, game_mode: GameMode,
) -> float:
    if not summary_path.exists():
        return 0
    return sum(
        row.get("estimated_cost_usd_total") or 0
        for row in map(json.loads, summary_path.read_text().splitlines())
        if (row.get("run_id"), row.get("model_key"), row.get("condition"), row.get("game_mode"))
        == (run_id, model_key, condition.value, game_mode.value)
    )


async def run_batch(
    adapter: ModelAdapter,
    condition: Condition,
    games: Iterable[tuple[str, GameState]],
    proposal_path: Path,
    summary_path: Path,
    *,
    run_id: str,
    model_key: str,
    game_mode: GameMode = GameMode.NORMAL,
    concurrency: int = 1,
    max_cost_usd: float | None = None,
    prices: tuple[float | None, float | None, float | None] = (0, 0, 0),
    metadata: dict[str, str] | None = None,
) -> tuple[GameResult, ...]:
    if concurrency < 1:
        raise ValueError("concurrency must be positive")
    if max_cost_usd is not None and None in prices:
        raise ValueError("--max-cost-usd requires configured model pricing")
    completed = completed_game_ids(summary_path, run_id, model_key, condition, game_mode)
    pending = [(game_id, state) for game_id, state in games if game_id not in completed]
    semaphore = asyncio.Semaphore(concurrency)

    async def run(item: tuple[str, GameState]) -> tuple[str, GameResult]:
        async with semaphore:
            return item[0], await run_game(
                adapter, condition, item[1], game_mode=game_mode, input_price_per_million=prices[0],
                output_price_per_million=prices[1], reasoning_price_per_million=prices[2],
            )

    spent = existing_cost(summary_path, run_id, model_key, condition, game_mode)
    written = []
    # ponytail: a concurrent batch can overshoot by at most concurrency games; reserve estimates if tighter control matters.
    for offset in range(0, len(pending), concurrency):
        if max_cost_usd is not None and spent >= max_cost_usd:
            raise RuntimeError(f"cost guard reached: ${spent:.6f} >= ${max_cost_usd:.6f}")
        results = await asyncio.gather(*(run(item) for item in pending[offset:offset + concurrency]))
        for game_id, result in results:
            spent += result.summary.estimated_cost_usd_total or 0
            append_result(proposal_path, summary_path, result, {
                **(metadata or {}), "run_id": run_id, "model_key": model_key,
                "condition": condition.value, "game_id": game_id,
            })
            written.append(result)
    return tuple(written)
