from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from benchmark.analysis.bootstrap import confidence_interval
from benchmark.analysis.dashboard import write_dashboard

METRICS = (
    "solve_at_6", "mean_round_score", "initial_valid_at_1", "initial_valid_at_3",
    "ig_efficiency", "search_regret", "ranking_regret", "repair_success_rate",
    "forfeit_rate",
)


def _read(paths: list[Path]) -> list[dict[str, Any]]:
    return [json.loads(line) for path in paths for line in path.read_text().splitlines() if line]


def _mean(values: list[float]) -> float | None:
    return mean(values) if values else None


def _proposal_metrics(rows: list[dict[str, Any]]) -> dict[str, float | None]:
    initial = [row for row in rows if row["proposal_type"] == "initial"]
    evaluations = [evaluation for row in initial for evaluation in row["evaluations"]]
    efficiencies, search, ranking = [], [], []
    for row in initial:
        gains = row["information_gain"]
        valid_gains = [gain for gain in gains if gain is not None]
        if valid_gains:
            search.append(row["ig_star"] - max(valid_gains))
        if gains and gains[0] is not None:
            if row["ig_star"] > 0:
                efficiencies.append(gains[0] / row["ig_star"])
            if valid_gains:
                ranking.append(max(valid_gains) - gains[0])
    return {
        "initial_valid_at_1": (
            sum(bool(row["evaluations"] and row["evaluations"][0]["status"] == "VALID") for row in initial)
            / len(initial) if initial else None
        ),
        "initial_valid_at_3": (
            sum(item["status"] == "VALID" for item in evaluations) / (3 * len(initial))
            if initial else None
        ),
        "ig_efficiency": _mean(efficiencies),
        "search_regret": _mean(search),
        "ranking_regret": _mean(ranking),
    }


def aggregate(summaries: list[dict[str, Any]], proposals: list[dict[str, Any]]) -> dict[str, Any]:
    proposal_metrics = _proposal_metrics(proposals)
    rounds_by_game: dict[str, int] = defaultdict(int)
    for row in proposals:
        rounds_by_game[row["game_id"]] = max(rounds_by_game[row["game_id"]], row["decision_round"])
    rounds = sum(rounds_by_game.values())
    return {
        "games": len(summaries),
        "solve_at_6": _mean([row["solved"] for row in summaries]),
        "mean_round_score": _mean([row["round_score"] for row in summaries]),
        **proposal_metrics,
        "repair_success_rate": (
            sum(row["repair_success_count"] for row in summaries)
            / sum(row["repair_attempt_count"] for row in summaries)
            if sum(row["repair_attempt_count"] for row in summaries) else None
        ),
        "forfeit_rate": sum(row["forfeit_count"] for row in summaries) / rounds if rounds else None,
    }


def _game_metric(summary: dict[str, Any], proposals: list[dict[str, Any]], metric: str) -> float | None:
    return aggregate([summary], proposals)[metric]


def _sample_metric(items: list[tuple[dict[str, Any], list[dict[str, Any]]]], metric: str) -> float | None:
    result = aggregate(
        [summary for summary, _ in items],
        [proposal for _, proposals in items for proposal in proposals],
    )
    if metric == "forfeit_rate":
        rounds = sum(max((row["decision_round"] for row in proposals), default=0) for _, proposals in items)
        return sum(summary["forfeit_count"] for summary, _ in items) / rounds if rounds else None
    return result[metric]


def _write_table(rows: list[dict[str, Any]], stem: Path, columns: list[str]) -> None:
    with stem.with_suffix(".csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    table = pa.Table.from_pylist(rows) if rows else pa.table({column: pa.array([], type=pa.string()) for column in columns})
    pq.write_table(table, stem.with_suffix(".parquet"))


def _svg(rows: list[dict[str, Any]], metric: str, path: Path) -> None:
    values = [(f'{row["model_key"]} {row["condition"]}', row[metric]) for row in rows if row[metric] is not None]
    width, height = 900, max(180, 60 + 28 * len(values))
    maximum = max((abs(value) for _, value in values), default=1) or 1
    bars = []
    for index, (label, value) in enumerate(values):
        y, bar = 45 + index * 28, 600 * abs(value) / maximum
        bars.append(f'<text x="10" y="{y + 14}">{label}</text><rect x="260" y="{y}" width="{bar:.1f}" height="18" fill="#4c78a8"/><text x="{270 + bar:.1f}" y="{y + 14}">{value:.4f}</text>')
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">'
        f'<style>text{{font:12px sans-serif}}</style><text x="10" y="22" font-size="16">{metric}</text>'
        + "".join(bars) + "</svg>\n"
    )


def analyze_results(results: Path, output: Path, *, resamples: int = 10_000, seed: int = 0) -> None:
    proposals = _read(sorted(results.rglob("proposals.jsonl")))
    summaries = _read(sorted(results.rglob("summaries.jsonl")))
    if not summaries:
        raise ValueError(f"no completed game summaries found under {results}")
    keys = [(row["model_key"], row["condition"], row["game_id"]) for row in summaries]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate completed model/condition/game records")

    proposal_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    summary_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in proposals:
        proposal_groups[row["model_key"], row["condition"]].append(row)
    for row in summaries:
        summary_groups[row["model_key"], row["condition"]].append(row)

    metric_rows = []
    for key in sorted(summary_groups):
        group_summaries, group_proposals = summary_groups[key], proposal_groups[key]
        row = {"model_key": key[0], "condition": key[1], **aggregate(group_summaries, group_proposals)}
        by_game = {summary["game_id"]: summary for summary in group_summaries}
        game_proposals = defaultdict(list)
        for proposal in group_proposals:
            game_proposals[proposal["game_id"]].append(proposal)
        items = [(summary, game_proposals[game_id]) for game_id, summary in sorted(by_game.items())]
        for offset, metric in enumerate(METRICS):
            low, high = confidence_interval(
                items, lambda sample, m=metric: _sample_metric(sample, m),
                resamples=resamples, seed=seed + offset,
            )
            row[f"{metric}_ci_low"], row[f"{metric}_ci_high"] = low, high
        metric_rows.append(row)

    age_counts: dict[tuple[str, str, int], list[int]] = defaultdict(lambda: [0, 0])
    accepted_rounds: dict[tuple[str, str, str], set[int]] = defaultdict(set)
    for row in proposals:
        if row.get("accepted_guess"):
            accepted_rounds[row["model_key"], row["condition"], row["game_id"]].add(row["decision_round"])
    for row in proposals:
        if row["proposal_type"] != "initial":
            continue
        for evaluation in row["evaluations"]:
            if evaluation["status"] in {"FORMAT_ERROR", "LEXICON_ERROR"}:
                continue
            ages = {
                row["decision_round"] - accepted_round
                for accepted_round in accepted_rounds[row["model_key"], row["condition"], row["game_id"]]
                if accepted_round < row["decision_round"]
            }
            for age in ages:
                age_counts[row["model_key"], row["condition"], age][1] += 1
            for age in set(evaluation["violated_constraint_ages"]):
                age_counts[row["model_key"], row["condition"], age][0] += 1
    age_rows = [{
        "model_key": key[0], "condition": key[1], "clue_age": key[2],
        "violations": counts[0], "exposures": counts[1],
        "violation_rate": counts[0] / counts[1] if counts[1] else None,
    } for key, counts in sorted(age_counts.items())]

    contrasts = []
    for model in sorted({key[0] for key in summary_groups}):
        named = {row["game_id"]: row for row in summary_groups.get((model, "hist_named"), [])}
        unnamed = {row["game_id"]: row for row in summary_groups.get((model, "hist_unnamed"), [])}
        ids = sorted(named.keys() & unnamed.keys())
        if not ids:
            continue
        for offset, metric in enumerate(METRICS):
            pairs = []
            for game_id in ids:
                left = _game_metric(named[game_id], [p for p in proposal_groups[model, "hist_named"] if p["game_id"] == game_id], metric)
                right = _game_metric(unnamed[game_id], [p for p in proposal_groups[model, "hist_unnamed"] if p["game_id"] == game_id], metric)
                if left is not None and right is not None:
                    pairs.append((left, right))
            delta = _mean([left - right for left, right in pairs])
            low, high = confidence_interval(pairs, lambda sample: _mean([a - b for a, b in sample]), resamples=resamples, seed=seed + offset)
            contrasts.append({"model_key": model, "contrast": "hist_named-hist_unnamed", "metric": metric,
                              "pairs": len(pairs), "delta": delta, "ci_low": low, "ci_high": high})

    output.mkdir(parents=True, exist_ok=True)
    _write_table(metric_rows, output / "metrics", list(metric_rows[0]))
    _write_table(age_rows, output / "constraint_age", ["model_key", "condition", "clue_age", "violations", "exposures", "violation_rate"])
    _write_table(contrasts, output / "paired_contrasts", ["model_key", "contrast", "metric", "pairs", "delta", "ci_low", "ci_high"])
    for metric in ("solve_at_6", "mean_round_score", "initial_valid_at_1", "ig_efficiency", "repair_success_rate"):
        _svg(metric_rows, metric, output / f"{metric}.svg")
    _svg(age_rows, "violation_rate", output / "constraint_age.svg")
    write_dashboard(metric_rows, age_rows, contrasts, output / "dashboard.html")
