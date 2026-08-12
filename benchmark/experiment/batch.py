from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Iterable
from pathlib import Path

from benchmark.experiment.runner import GameResult, append_result, run_game
from benchmark.types import Condition, GameMode, GameState, ModelAdapter

RunKey = tuple[str, str, str, str, str]


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"malformed JSON in {path}:{number}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"expected object in {path}:{number}")
        rows.append(row)
    return rows


def result_key(row: dict) -> RunKey:
    required = ("run_id", "model_key", "condition", "game_mode", "game_id")
    missing = [name for name in required if not row.get(name)]
    if missing:
        raise ValueError(f"result record missing {', '.join(missing)}")
    return tuple(row[name] for name in required)  # type: ignore[return-value]


def completed_rows(summary_path: Path) -> list[dict]:
    rows = read_jsonl(summary_path)
    keys = [result_key(row) for row in rows]
    if len(keys) != len(set(keys)):
        raise ValueError(f"duplicate completed summary in {summary_path}")
    return rows


def completed_game_ids(
    summary_path: Path, run_id: str, model_key: str, condition: Condition, game_mode: GameMode,
) -> set[str]:
    prefix = run_id, model_key, condition.value, game_mode.value
    return {result_key(row)[4] for row in completed_rows(summary_path) if result_key(row)[:4] == prefix}


def existing_cost(
    summary_path: Path, run_id: str, model_key: str, condition: Condition, game_mode: GameMode,
) -> float:
    prefix = run_id, model_key, condition.value, game_mode.value
    return sum(
        row.get("estimated_cost_usd_total") or 0
        for row in completed_rows(summary_path) if result_key(row)[:4] == prefix
    )


def partial_proposals(proposal_path: Path, summary_path: Path) -> tuple[list[dict], set[RunKey]]:
    proposals = read_jsonl(proposal_path)
    complete = {result_key(row) for row in completed_rows(summary_path)}
    orphan_keys = {result_key(row) for row in proposals if result_key(row) not in complete}
    return proposals, orphan_keys


def clean_partial_proposals(proposal_path: Path, summary_path: Path) -> tuple[int, int]:
    proposals, orphan_keys = partial_proposals(proposal_path, summary_path)
    if not orphan_keys:
        return 0, 0
    kept = [row for row in proposals if result_key(row) not in orphan_keys]
    temporary = proposal_path.with_suffix(proposal_path.suffix + ".tmp")
    with temporary.open("w") as handle:
        for row in kept:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, proposal_path)
    return len(proposals) - len(kept), len(orphan_keys)


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
    progress_every: int = 10,
) -> tuple[GameResult, ...]:
    if concurrency < 1:
        raise ValueError("concurrency must be positive")
    if max_cost_usd is not None and None in prices:
        raise ValueError("--max-cost-usd requires configured model pricing")
    games = tuple(games)
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
    prior_rows = [row for row in completed_rows(summary_path) if result_key(row)[:4] == (
        run_id, model_key, condition.value, game_mode.value,
    )]
    solved = sum(bool(row.get("solved")) for row in prior_rows)
    written = []
    total = len(games)
    # ponytail: a concurrent batch can overshoot by at most concurrency games; reserve estimates if tighter control matters.
    for offset in range(0, len(pending), concurrency):
        if max_cost_usd is not None and spent >= max_cost_usd:
            print(f"Cost guard reached.\nCompleted: {len(completed)}/{total}\nRecorded cost: ${spent:.4f}\nRemaining games can be resumed with the same run ID.")
            break
        results = await asyncio.gather(*(run(item) for item in pending[offset:offset + concurrency]))
        for game_id, result in results:
            spent += result.summary.estimated_cost_usd_total or 0
            append_result(proposal_path, summary_path, result, {
                **(metadata or {}), "run_id": run_id, "model_key": model_key,
                "condition": condition.value, "game_id": game_id,
            })
            written.append(result)
            completed.add(game_id)
            solved += result.summary.solved
            game_cost = result.summary.estimated_cost_usd_total
            cost = "unknown" if game_cost is None else f"${game_cost:.4f}"
            print(
                f"[{len(completed)}/{total}] {game_id} complete | "
                f"solved={'yes' if result.summary.solved else 'no'} | "
                f"score={result.summary.round_score} | cost={cost} | total=${spent:.4f}"
            )
            if progress_every and len(completed) % progress_every == 0:
                print(
                    f"Progress: {len(completed)}/{total} ({100 * len(completed) / total:.1f}%) | "
                    f"Pending: {total - len(completed)} | Solved so far: {solved}/{len(completed)} "
                    f"({100 * solved / len(completed):.1f}%) | Estimated cost so far: ${spent:.2f}"
                )
    return tuple(written)
