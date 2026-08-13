from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from benchmark.analysis.bootstrap import confidence_interval
from benchmark.analysis.dashboard import write_dashboard
from benchmark.experiment.batch import result_key
from benchmark.types import Condition, GameMode

METRICS = (
    "solve_at_6", "mean_round_score", "played_guesses_per_game",
    "initial_action_valid_at_1", "initial_action_valid_at_3",
    "constraint_consistent_at_1", "constraint_consistent_at_3",
    "strict_valid_at_1", "strict_valid_at_3", "ig_efficiency", "search_regret",
    "ranking_regret", "total_regret", "repair_success_rate", "forfeits_per_game",
    "forfeit_rate", "repeat_rate",
)

REASONING_EFFECT_METRICS = (
    "solve_at_6", "mean_round_score", "constraint_consistent_at_1", "strict_valid_at_1",
    "repair_success_rate", "forfeits_per_game", "ig_efficiency",
    "mean_reasoning_tokens_per_game", "mean_latency_ms_per_game", "mean_cost_usd_per_game",
)


def _model_family(model_key: str) -> str:
    return model_key.removesuffix("_medium")


def _reasoning_setting(model_key: str) -> str:
    return "medium" if model_key.endswith("_medium") else "baseline"


def _read(paths: list[Path]) -> list[dict[str, Any]]:
    return [json.loads(line) for path in paths for line in path.read_text().splitlines() if line]


def _mean(values: list[float]) -> float | None:
    return mean(values) if values else None


def _proposal_metrics(rows: list[dict[str, Any]]) -> dict[str, float | None]:
    initial = [row for row in rows if row["proposal_type"] == "initial"]
    evaluations = [evaluation for row in initial for evaluation in row["evaluations"]]
    top1 = [row["evaluations"][0] if row["evaluations"] else None for row in initial]
    action_evaluations = [item for item in evaluations if item["action_status"] == "VALID"]
    efficiencies, search, ranking, total = [], [], [], []
    for row in initial:
        gains = row["information_gain"]
        valid_gains = [gain for gain in gains if gain is not None]
        if valid_gains:
            search.append(row["ig_oracle"] - max(valid_gains))
        if gains and gains[0] is not None:
            if row["ig_oracle"] > 0:
                efficiencies.append(gains[0] / row["ig_oracle"])
            if valid_gains:
                ranking.append(max(valid_gains) - gains[0])
            total.append(row["ig_oracle"] - gains[0])
    return {
        "initial_action_valid_at_1": (
            sum(bool(item and item["action_status"] == "VALID") for item in top1) / len(initial)
            if initial else None
        ),
        "initial_action_valid_at_3": (
            len(action_evaluations) / (3 * len(initial))
            if initial else None
        ),
        "constraint_consistent_at_1": _mean([
            float(item["constraint_consistent"]) for item in top1
            if item and item["action_status"] == "VALID"
        ]),
        "constraint_consistent_at_3": _mean([
            float(item["constraint_consistent"]) for item in action_evaluations
        ]),
        "strict_valid_at_1": (
            sum(bool(item and item["action_status"] == "VALID" and item["constraint_consistent"])
                for item in top1) / len(initial) if initial else None
        ),
        "strict_valid_at_3": (
            sum(bool(item["constraint_consistent"]) for item in action_evaluations)
            / (3 * len(initial)) if initial else None
        ),
        "ig_efficiency": _mean(efficiencies),
        "search_regret": _mean(search),
        "ranking_regret": _mean(ranking),
        "total_regret": _mean(total),
        "repeat_rate": _mean([
            float("REPEAT_ACCEPTED_GUESS" in item["diagnostics"]) for item in action_evaluations
        ]),
    }


def aggregate(summaries: list[dict[str, Any]], proposals: list[dict[str, Any]]) -> dict[str, Any]:
    proposal_metrics = _proposal_metrics(proposals)
    rounds_by_game: dict[str, int] = defaultdict(int)
    for row in proposals:
        rounds_by_game[row["game_id"]] = max(rounds_by_game[row["game_id"]], row["decision_round"])
    rounds = sum(rounds_by_game.values())
    reasoning_response = [row["reasoning_tokens"] for row in proposals if row.get("reasoning_tokens") is not None]
    reasoning_game = [row.get("reasoning_tokens_total") or 0 for row in summaries]
    latency_response = [row["latency_ms"] for row in proposals if row.get("latency_ms") is not None]
    latency_game = [row["latency_ms_total"] for row in summaries if row.get("latency_ms_total") is not None]
    costs = [row["estimated_cost_usd_total"] for row in summaries if row.get("estimated_cost_usd_total") is not None]
    return {
        "games": len(summaries),
        "solve_at_6": _mean([row["solved"] for row in summaries]),
        "mean_round_score": _mean([row["round_score"] for row in summaries]),
        "played_guesses_per_game": _mean([row["played_guess_count"] for row in summaries]),
        **proposal_metrics,
        "repair_success_rate": (
            sum(row["repair_success_count"] for row in summaries)
            / sum(row["repair_attempt_count"] for row in summaries)
            if sum(row["repair_attempt_count"] for row in summaries) else None
        ),
        "forfeit_rate": sum(row["forfeit_count"] for row in summaries) / rounds if rounds else None,
        "forfeits_per_game": _mean([row["forfeit_count"] for row in summaries]),
        "mean_reasoning_tokens_per_response": _mean(reasoning_response),
        "median_reasoning_tokens_per_response": median(reasoning_response) if reasoning_response else None,
        "mean_reasoning_tokens_per_game": _mean(reasoning_game),
        "median_reasoning_tokens_per_game": median(reasoning_game) if reasoning_game else None,
        "total_reasoning_tokens": sum(reasoning_game),
        "mean_latency_ms_per_response": _mean(latency_response),
        "mean_latency_ms_per_game": _mean(latency_game),
        "mean_cost_usd_per_game": _mean(costs),
        "total_cost_usd": sum(costs) if len(costs) == len(summaries) else None,
    }


def _game_metric(summary: dict[str, Any], proposals: list[dict[str, Any]], metric: str) -> float | None:
    return aggregate([summary], proposals)[metric]


def _sample_metric(items: list[tuple[dict[str, Any], list[dict[str, Any]]]], metric: str) -> float | None:
    result = aggregate(
        [summary for summary, _ in items],
        [proposal for _, proposals in items for proposal in proposals],
    )
    return result[metric]


def _write_table(rows: list[dict[str, Any]], stem: Path, columns: list[str]) -> None:
    with stem.with_suffix(".csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    table = pa.Table.from_pylist(rows) if rows else pa.table({column: pa.array([], type=pa.string()) for column in columns})
    pq.write_table(table, stem.with_suffix(".parquet"))


def _svg(rows: list[dict[str, Any]], metric: str, path: Path) -> None:
    values = [(f'{row["model_key"]} {row["condition"]} {row["game_mode"]}', row[metric]) for row in rows if row[metric] is not None]
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
    completed = {result_key(row) for row in summaries}
    proposals = [row for row in proposals if result_key(row) in completed]
    if any("game_mode" not in row for row in summaries + proposals) or any(
        "action_status" not in evaluation for row in proposals for evaluation in row.get("evaluations", [])
    ):
        raise ValueError("results use the pre-mode schema; analyze them with the matching benchmark version")
    keys = [(row["model_key"], row["condition"], row["game_mode"], row["game_id"]) for row in summaries]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate completed model/condition/game records")

    proposal_groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    summary_groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in proposals:
        proposal_groups[row["model_key"], row["condition"], row["game_mode"]].append(row)
    for row in summaries:
        summary_groups[row["model_key"], row["condition"], row["game_mode"]].append(row)

    metric_rows = []
    for key in sorted(summary_groups):
        group_summaries, group_proposals = summary_groups[key], proposal_groups[key]
        row = {"model_key": key[0], "model_family": _model_family(key[0]),
               "reasoning_setting": _reasoning_setting(key[0]),
               "condition": key[1], "game_mode": key[2],
               **aggregate(group_summaries, group_proposals)}
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

    def game_values(key: tuple[str, str, str], metric: str) -> dict[str, float]:
        grouped = defaultdict(list)
        for proposal in proposal_groups[key]:
            grouped[proposal["game_id"]].append(proposal)
        return {
            summary["game_id"]: value
            for summary in summary_groups[key]
            if (value := _game_metric(summary, grouped[summary["game_id"]], metric)) is not None
        }

    def require_paired(left: tuple[str, str, str], right: tuple[str, str, str]) -> None:
        left_rows, right_rows = summary_groups[left], summary_groups[right]
        if {row["game_id"] for row in left_rows} != {row["game_id"] for row in right_rows}:
            raise ValueError(f"paired comparison has different game IDs: {left} vs {right}")
        for field in ("benchmark_version", "prompt_version", "requested_model_id", "provider",
                      "manifest_hash", "temperature"):
            left_values = {row.get(field) for row in left_rows}
            right_values = {row.get(field) for row in right_rows}
            if left_values != right_values and left_values != {None} and right_values != {None}:
                raise ValueError(f"paired comparison differs in {field}: {left} vs {right}")

    reasoning_effects = []
    for family in ("gpt5", "gpt56"):
        for condition in Condition:
            for mode in GameMode:
                baseline, medium = (family, condition.value, mode.value), (
                    f"{family}_medium", condition.value, mode.value,
                )
                if baseline not in summary_groups or medium not in summary_groups:
                    continue
                require_paired(baseline, medium)
                for offset, metric in enumerate(REASONING_EFFECT_METRICS):
                    left, right = game_values(baseline, metric), game_values(medium, metric)
                    ids = sorted(left.keys() & right.keys())
                    pairs = [(left[game_id], right[game_id]) for game_id in ids]
                    low, high = confidence_interval(
                        pairs, lambda sample: _mean([medium_value - base for base, medium_value in sample]),
                        resamples=resamples, seed=seed + offset,
                    )
                    reasoning_effects.append({
                        "model_family": family, "condition": condition.value,
                        "game_mode": mode.value, "metric": metric, "pairs": len(pairs),
                        "delta_medium_minus_baseline": _mean([b - a for a, b in pairs]),
                        "ci_low": low, "ci_high": high,
                    })

    enforcement = []
    penalties: dict[tuple[str, str, str], dict[str, float]] = {}
    for model_key in ("gpt5", "gpt5_medium", "gpt56", "gpt56_medium"):
        for condition in Condition:
            normal = model_key, condition.value, "normal"
            strict = model_key, condition.value, "strict"
            if normal not in summary_groups or strict not in summary_groups:
                continue
            require_paired(normal, strict)
            normal_solve, strict_solve = game_values(normal, "solve_at_6"), game_values(strict, "solve_at_6")
            normal_score, strict_score = game_values(normal, "mean_round_score"), game_values(strict, "mean_round_score")
            ids = sorted(normal_solve.keys() & strict_solve.keys() & normal_score.keys() & strict_score.keys())
            solve_pairs = [(normal_solve[i], strict_solve[i]) for i in ids]
            score_pairs = [(normal_score[i], strict_score[i]) for i in ids]
            solve_penalty = _mean([normal_value - strict_value for normal_value, strict_value in solve_pairs])
            score_penalty = _mean([strict_value - normal_value for normal_value, strict_value in score_pairs])
            enforcement.append({
                "model_family": _model_family(model_key),
                "reasoning_setting": _reasoning_setting(model_key), "condition": condition.value,
                "pairs": len(ids), "normal_solve": _mean(list(normal_solve.values())),
                "strict_solve": _mean(list(strict_solve.values())), "solve_penalty": solve_penalty,
                "normal_score": _mean(list(normal_score.values())),
                "strict_score": _mean(list(strict_score.values())), "score_penalty": score_penalty,
            })
            penalties[_model_family(model_key), condition.value, _reasoning_setting(model_key)] = {
                game_id: normal_solve[game_id] - strict_solve[game_id] for game_id in ids
            }

    penalty_reductions = []
    for family in ("gpt5", "gpt56"):
        for condition in Condition:
            baseline = penalties.get((family, condition.value, "baseline"), {})
            medium = penalties.get((family, condition.value, "medium"), {})
            ids = sorted(baseline.keys() & medium.keys())
            pairs = [(baseline[i], medium[i]) for i in ids]
            if not pairs:
                continue
            low, high = confidence_interval(
                pairs, lambda sample: _mean([base - med for base, med in sample]),
                resamples=resamples, seed=seed,
            )
            penalty_reductions.append({
                "model_family": family, "condition": condition.value, "pairs": len(pairs),
                "baseline_penalty": _mean([a for a, _ in pairs]),
                "medium_penalty": _mean([b for _, b in pairs]),
                "penalty_reduction": _mean([a - b for a, b in pairs]),
                "ci_low": low, "ci_high": high,
            })

    age_counts: dict[tuple[str, str, str, int], list[int]] = defaultdict(lambda: [0, 0])
    played_rounds: dict[tuple[str, str, str, str], set[int]] = defaultdict(set)
    for row in proposals:
        if row.get("played"):
            played_rounds[row["model_key"], row["condition"], row["game_mode"], row["game_id"]].add(row["decision_round"])
    for row in proposals:
        if row["proposal_type"] != "initial":
            continue
        for evaluation in row["evaluations"]:
            if evaluation["action_status"] != "VALID":
                continue
            ages = {
                row["decision_round"] - played_round
                for played_round in played_rounds[row["model_key"], row["condition"], row["game_mode"], row["game_id"]]
                if played_round < row["decision_round"]
            }
            for age in ages:
                age_counts[row["model_key"], row["condition"], row["game_mode"], age][1] += 1
            for age in set(evaluation["violated_constraint_ages"]):
                age_counts[row["model_key"], row["condition"], row["game_mode"], age][0] += 1
    age_rows = [{
        "model_key": key[0], "condition": key[1], "game_mode": key[2], "clue_age": key[3],
        "violations": counts[0], "exposures": counts[1],
        "violation_rate": counts[0] / counts[1] if counts[1] else None,
    } for key, counts in sorted(age_counts.items())]

    round_counts: dict[tuple[str, str, str, int], list[int]] = defaultdict(lambda: [0, 0])
    for row in proposals:
        if row["proposal_type"] != "initial":
            continue
        key = row["model_key"], row["condition"], row["game_mode"], row["decision_round"]
        for evaluation in row["evaluations"]:
            if evaluation["action_status"] == "VALID":
                round_counts[key][1] += 1
                round_counts[key][0] += bool(evaluation["constraint_consistent"])
    round_rows = [{
        "model_key": key[0], "condition": key[1], "game_mode": key[2],
        "decision_round": key[3], "consistent": counts[0], "action_valid": counts[1],
        "consistency_rate": counts[0] / counts[1] if counts[1] else None,
    } for key, counts in sorted(round_counts.items())]

    contrasts = []
    for model, mode in sorted({(key[0], key[2]) for key in summary_groups}):
        named_key, unnamed_key = (model, "hist_named", mode), (model, "hist_unnamed", mode)
        named = {row["game_id"]: row for row in summary_groups.get(named_key, [])}
        unnamed = {row["game_id"]: row for row in summary_groups.get(unnamed_key, [])}
        if named and unnamed:
            require_paired(named_key, unnamed_key)
        ids = sorted(named.keys() & unnamed.keys())
        if not ids:
            continue
        for offset, metric in enumerate(METRICS):
            pairs = []
            for game_id in ids:
                left = _game_metric(named[game_id], [p for p in proposal_groups[model, "hist_named", mode] if p["game_id"] == game_id], metric)
                right = _game_metric(unnamed[game_id], [p for p in proposal_groups[model, "hist_unnamed", mode] if p["game_id"] == game_id], metric)
                if left is not None and right is not None:
                    pairs.append((left, right))
            delta = _mean([left - right for left, right in pairs])
            low, high = confidence_interval(pairs, lambda sample: _mean([a - b for a, b in sample]), resamples=resamples, seed=seed + offset)
            contrasts.append({"model_key": model, "game_mode": mode,
                              "contrast": "hist_named-hist_unnamed", "metric": metric,
                              "pairs": len(pairs), "delta": delta, "ci_low": low, "ci_high": high})

    output.mkdir(parents=True, exist_ok=True)
    _write_table(metric_rows, output / "metrics", list(metric_rows[0]))
    _write_table(age_rows, output / "constraint_age", ["model_key", "condition", "game_mode", "clue_age", "violations", "exposures", "violation_rate"])
    _write_table(round_rows, output / "consistency_by_round", ["model_key", "condition", "game_mode", "decision_round", "consistent", "action_valid", "consistency_rate"])
    _write_table(contrasts, output / "paired_contrasts", ["model_key", "game_mode", "contrast", "metric", "pairs", "delta", "ci_low", "ci_high"])
    _write_table(reasoning_effects, output / "reasoning_effects", [
        "model_family", "condition", "game_mode", "metric", "pairs",
        "delta_medium_minus_baseline", "ci_low", "ci_high",
    ])
    _write_table(enforcement, output / "enforcement_penalty", [
        "model_family", "reasoning_setting", "condition", "pairs", "normal_solve",
        "strict_solve", "solve_penalty", "normal_score", "strict_score", "score_penalty",
    ])
    _write_table(penalty_reductions, output / "penalty_reduction", [
        "model_family", "condition", "pairs", "baseline_penalty", "medium_penalty",
        "penalty_reduction", "ci_low", "ci_high",
    ])
    reasoning_columns = [
        "condition", "game_mode", "reasoning_setting", "solve_at_6",
        "constraint_consistent_at_1", "strict_valid_at_1", "forfeits_per_game",
        "ig_efficiency", "mean_cost_usd_per_game",
    ]
    for family in ("gpt5", "gpt56"):
        _write_table(
            [{column: row[column] for column in reasoning_columns} for row in metric_rows
             if row["model_family"] == family],
            output / f"{family}_reasoning_benchmark", reasoning_columns,
        )
    for metric in ("solve_at_6", "mean_round_score", "initial_action_valid_at_1",
                   "constraint_consistent_at_1", "strict_valid_at_1", "ig_efficiency",
                   "repair_success_rate"):
        _svg(metric_rows, metric, output / f"{metric}.svg")
    _svg(age_rows, "violation_rate", output / "constraint_age.svg")
    write_dashboard(metric_rows, age_rows, contrasts, output / "dashboard.html")
