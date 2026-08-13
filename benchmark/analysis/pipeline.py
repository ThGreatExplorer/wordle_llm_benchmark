from __future__ import annotations

import csv
import json
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from benchmark.analysis.bootstrap import confidence_interval, independent_difference_interval
from benchmark.analysis.schema import ANALYSIS_SCHEMA_VERSION, validate_analysis_snapshot
from benchmark.experiment.batch import result_key
from benchmark.experiment.manifests import file_sha256
from benchmark.types import Condition, GameMode

METRICS = (
    "solve_at_6", "mean_round_score", "played_guesses_per_game", "played_guesses_among_wins",
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
OPENAI_MODEL_KEYS = {"gpt4o", "gpt5", "gpt56", "gpt5_medium", "gpt56_medium"}


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
    repairs = [row for row in rows if row["proposal_type"] == "repair"]
    repair_by_round = {(row["game_id"], row["decision_round"]): row for row in repairs}
    repair_causes: dict[str, list[bool]] = defaultdict(list)
    for row in initial:
        top = row["evaluations"][0] if row["evaluations"] else None
        if row.get("protocol_error"):
            cause = "protocol"
        elif top and top["action_status"] != "VALID":
            cause = "format" if top["action_status"] == "FORMAT_ERROR" else "lexicon"
        elif top and not top["constraint_consistent"] and row["game_mode"] == "strict":
            cause = "constraint"
        else:
            continue
        repair = repair_by_round.get((row["game_id"], row["decision_round"]))
        repair_causes[cause].append(bool(repair and repair.get("played")))
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
        "protocol_error_rate": _mean([float(bool(row.get("protocol_error"))) for row in initial]),
        "format_error_rate": _mean([float(item["action_status"] == "FORMAT_ERROR") for item in evaluations]),
        "lexicon_error_rate": _mean([float(item["action_status"] == "LEXICON_ERROR") for item in evaluations]),
        **{f"repair_success_{cause}": _mean([float(value) for value in repair_causes[cause]])
           for cause in ("protocol", "format", "lexicon", "constraint")},
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
        "played_guesses_among_wins": _mean([
            row["played_guess_count"] for row in summaries if row["solved"]
        ]),
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


def _metric_components(
    summary: dict[str, Any], proposals: list[dict[str, Any]], metric: str,
) -> tuple[float, int]:
    initial = [row for row in proposals if row["proposal_type"] == "initial"]
    evaluations = [item for row in initial for item in row["evaluations"]]
    top1 = [row["evaluations"][0] if row["evaluations"] else None for row in initial]
    valid = [item for item in evaluations if item["action_status"] == "VALID"]
    simple = {
        "solve_at_6": (float(summary["solved"]), 1),
        "mean_round_score": (summary["round_score"], 1),
        "played_guesses_per_game": (summary["played_guess_count"], 1),
        "played_guesses_among_wins": (
            summary["played_guess_count"] if summary["solved"] else 0, int(summary["solved"])),
        "repair_success_rate": (summary["repair_success_count"], summary["repair_attempt_count"]),
        "forfeits_per_game": (summary["forfeit_count"], 1),
        "forfeit_rate": (summary["forfeit_count"], max((row["decision_round"] for row in proposals), default=0)),
        "initial_action_valid_at_1": (
            sum(bool(item and item["action_status"] == "VALID") for item in top1), len(initial)),
        "initial_action_valid_at_3": (len(valid), 3 * len(initial)),
        "constraint_consistent_at_1": (
            sum(bool(item["constraint_consistent"]) for item in top1
                if item and item["action_status"] == "VALID"),
            sum(bool(item and item["action_status"] == "VALID") for item in top1)),
        "constraint_consistent_at_3": (sum(bool(item["constraint_consistent"]) for item in valid), len(valid)),
        "strict_valid_at_1": (
            sum(bool(item and item["action_status"] == "VALID" and item["constraint_consistent"])
                for item in top1), len(initial)),
        "strict_valid_at_3": (sum(bool(item["constraint_consistent"]) for item in valid), 3 * len(initial)),
        "repeat_rate": (
            sum("REPEAT_ACCEPTED_GUESS" in item["diagnostics"] for item in valid), len(valid)),
    }
    if metric in simple:
        return simple[metric]
    values = []
    for row in initial:
        gains = row["information_gain"]
        valid_gains = [gain for gain in gains if gain is not None]
        if metric == "search_regret" and valid_gains:
            values.append(row["ig_oracle"] - max(valid_gains))
        elif gains and gains[0] is not None:
            if metric == "ig_efficiency" and row["ig_oracle"] > 0:
                values.append(gains[0] / row["ig_oracle"])
            elif metric == "ranking_regret" and valid_gains:
                values.append(max(valid_gains) - gains[0])
            elif metric == "total_regret":
                values.append(row["ig_oracle"] - gains[0])
    return sum(values), len(values)


def _write_table(rows: list[dict[str, Any]], stem: Path, columns: list[str]) -> None:
    stem.parent.mkdir(parents=True, exist_ok=True)
    if rows and "split" in rows[0] and "split" not in columns:
        columns = [*columns, "split"]
    with stem.with_suffix(".csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    table = pa.Table.from_pylist(rows) if rows else pa.table({column: pa.array([], type=pa.string()) for column in columns})
    pq.write_table(table, stem.with_suffix(".parquet"))


def _secrets(run_metadata: list[dict[str, Any]]) -> dict[tuple[str, str], str]:
    secrets = {}
    for metadata in run_metadata:
        name = metadata.get("selected_manifest")
        if not name:
            continue
        path = Path("data/manifests") / name
        if not path.exists():
            raise ValueError(f"selected manifest not found: {path}")
        expected = metadata.get("selected_manifest_hash") or metadata.get("manifest_hashes", {}).get(name)
        if expected and file_sha256(path) != expected:
            raise ValueError(f"selected manifest hash differs: {path}")
        for row in _read([path]):
            secrets[metadata["run_id"], row["game_id"]] = row["secret"]
    return secrets


def _processed_rows(
    summaries: list[dict[str, Any]], proposals: list[dict[str, Any]],
    run_metadata: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    metadata = {row.get("run_id"): row for row in run_metadata}
    secrets = _secrets(run_metadata)
    by_game: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in proposals:
        by_game[row["run_id"], row["game_id"]].append(row)
    games = []
    for summary in summaries:
        meta = metadata.get(summary["run_id"], {})
        game_rows = by_game[summary["run_id"], summary["game_id"]]
        games.append({
            **summary,
            "exact_model_id": summary.get("requested_model_id") or meta.get("requested_model_id"),
            "split": meta.get("split"),
            "reasoning_setting": _reasoning_setting(summary["model_key"]),
            "reasoning_effort": summary.get("reasoning_effort") or meta.get("reasoning_effort")
                                or meta.get("selected_model_config", {}).get("reasoning_effort"),
            "secret": secrets.get((summary["run_id"], summary["game_id"])),
            "played_guesses": [row.get("played_guess") for row in sorted(
                game_rows, key=lambda row: (row["decision_round"], row["proposal_type"] == "repair")
            ) if row.get("played")],
        })
    flat = []
    for row in proposals:
        meta = metadata.get(row["run_id"], {})
        evaluations, gains = row.get("evaluations", []), row.get("information_gain", [])
        item = {
            key: value for key, value in row.items()
            if key not in {"evaluations", "information_gain", "provider_metadata"}
        }
        item |= {
            "split": meta.get("split"),
            "reasoning_setting": _reasoning_setting(row["model_key"]),
            "reasoning_effort": row.get("reasoning_effort") or meta.get("reasoning_effort")
                                or meta.get("selected_model_config", {}).get("reasoning_effort"),
            "top1_played": bool(row.get("played")),
            "information_gain_top1": gains[0] if gains else None,
            "repeat_diagnostic": bool(evaluations and "REPEAT_ACCEPTED_GUESS" in evaluations[0].get("diagnostics", [])),
        }
        for index in range(3):
            evaluation = evaluations[index] if index < len(evaluations) else {}
            item |= {
                f"top{index + 1}": evaluation.get("normalized"),
                f"top{index + 1}_raw": evaluation.get("raw"),
                f"top{index + 1}_action_status": evaluation.get("action_status"),
                f"top{index + 1}_action_valid": evaluation.get("action_status") == "VALID",
                f"top{index + 1}_constraint_consistent": evaluation.get("constraint_consistent"),
                f"top{index + 1}_violated_constraint_ages": evaluation.get("violated_constraint_ages", []),
                f"top{index + 1}_diagnostics": evaluation.get("diagnostics", []),
                f"information_gain_top{index + 1}": gains[index] if index < len(gains) else None,
            }
        flat.append(item)
    return games, flat


def _result_paths(
    results: Path, *, provider: str | None, split: str | None,
    model_prefixes: tuple[str, ...],
) -> tuple[list[Path], list[Path], list[dict[str, Any]]]:
    if (results / "summaries.jsonl").exists():
        metadata = json.loads((results / "metadata.json").read_text()) if (results / "metadata.json").exists() else {}
        return [results / "proposals.jsonl"], [results / "summaries.jsonl"], ([metadata] if metadata else [])
    directories = []
    metadata_rows = []
    for metadata_path in sorted(results.glob("*/metadata.json")):
        metadata = json.loads(metadata_path.read_text())
        if provider and metadata.get("provider") != provider:
            if not (provider == "openai" and metadata.get("provider") is None
                    and metadata.get("model_key") in OPENAI_MODEL_KEYS):
                continue
        if split and metadata.get("split") != split:
            continue
        if model_prefixes and not str(metadata.get("model_key", "")).startswith(model_prefixes):
            continue
        directories.append(metadata_path.parent)
        metadata_rows.append(metadata)
    return (
        [directory / "proposals.jsonl" for directory in directories if (directory / "proposals.jsonl").exists()],
        [directory / "summaries.jsonl" for directory in directories if (directory / "summaries.jsonl").exists()],
        metadata_rows,
    )


def analyze_results(
    results: Path, output: Path, *, resamples: int = 10_000, seed: int = 0,
    provider: str | None = None, split: str | None = None,
    model_prefixes: tuple[str, ...] = (),
) -> None:
    proposal_paths, summary_paths, run_metadata = _result_paths(
        results, provider=provider, split=split, model_prefixes=model_prefixes,
    )
    proposals = _read(proposal_paths)
    summaries = _read(summary_paths)
    if not summaries:
        raise ValueError(f"no completed game summaries found under {results}")
    completed = {result_key(row) for row in summaries}
    proposals = [row for row in proposals if result_key(row) in completed]
    completed_by_run: dict[str, int] = defaultdict(int)
    solved_by_run: dict[str, int] = defaultdict(int)
    cost_by_run: dict[str, float] = defaultdict(float)
    for row in summaries:
        completed_by_run[row["run_id"]] += 1
        solved_by_run[row["run_id"]] += bool(row.get("solved"))
        cost_by_run[row["run_id"]] += row.get("estimated_cost_usd_total") or 0
    coverage_rows = [{
        "run_id": metadata.get("run_id"), "model_key": metadata.get("model_key"),
        "condition": metadata.get("condition"), "game_mode": metadata.get("game_mode"),
        "split": metadata.get("split"), "reasoning_effort": (
            metadata.get("reasoning_effort")
            or metadata.get("selected_model_config", {}).get("reasoning_effort")
        ),
        "requested": metadata.get("requested_games"),
        "completed": completed_by_run[metadata.get("run_id")],
        "pending": ((metadata.get("requested_games") or 0) - completed_by_run[metadata.get("run_id")]),
        "complete": completed_by_run[metadata.get("run_id")] == metadata.get("requested_games"),
        "solved": solved_by_run[metadata.get("run_id")],
        "recorded_cost_usd": cost_by_run[metadata.get("run_id")],
    } for metadata in run_metadata]
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
               "condition": key[1], "game_mode": key[2], "split": split,
               **aggregate(group_summaries, group_proposals)}
        by_game = {summary["game_id"]: summary for summary in group_summaries}
        game_proposals = defaultdict(list)
        for proposal in group_proposals:
            game_proposals[proposal["game_id"]].append(proposal)
        for offset, metric in enumerate(METRICS):
            components = [
                _metric_components(summary, game_proposals[game_id], metric)
                for game_id, summary in sorted(by_game.items())
            ]
            low, high = confidence_interval(
                components,
                lambda sample: (
                    sum(numerator for numerator, _ in sample)
                    / sum(denominator for _, denominator in sample)
                    if sum(denominator for _, denominator in sample) else None
                ),
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

    def validate_pair(left: tuple[str, str, str], right: tuple[str, str, str]) -> None:
        left_rows, right_rows = summary_groups[left], summary_groups[right]
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
                validate_pair(baseline, medium)
                for offset, metric in enumerate(REASONING_EFFECT_METRICS):
                    left, right = game_values(baseline, metric), game_values(medium, metric)
                    ids = sorted(left.keys() & right.keys())
                    pairs = [(left[game_id], right[game_id]) for game_id in ids]
                    low, high = confidence_interval(
                        pairs, lambda sample: _mean([medium_value - base for base, medium_value in sample]),
                        resamples=resamples, seed=seed + offset,
                    )
                    left_ids = {row["game_id"] for row in summary_groups[baseline]}
                    right_ids = {row["game_id"] for row in summary_groups[medium]}
                    reasoning_effects.append({
                        "model_family": family, "condition": condition.value,
                        "game_mode": mode.value, "metric": metric, "pairs": len(pairs),
                        "baseline_games": len(left_ids), "medium_games": len(right_ids),
                        "pair_complete": left_ids == right_ids,
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
            validate_pair(normal, strict)
            normal_solve, strict_solve = game_values(normal, "solve_at_6"), game_values(strict, "solve_at_6")
            normal_score, strict_score = game_values(normal, "mean_round_score"), game_values(strict, "mean_round_score")
            ids = sorted(normal_solve.keys() & strict_solve.keys() & normal_score.keys() & strict_score.keys())
            solve_pairs = [(normal_solve[i], strict_solve[i]) for i in ids]
            score_pairs = [(normal_score[i], strict_score[i]) for i in ids]
            solve_penalty = _mean([normal_value - strict_value for normal_value, strict_value in solve_pairs])
            score_penalty = _mean([strict_value - normal_value for normal_value, strict_value in score_pairs])
            solve_low, solve_high = confidence_interval(
                solve_pairs,
                lambda sample: _mean([normal_value - strict_value for normal_value, strict_value in sample]),
                resamples=resamples, seed=seed,
            )
            score_low, score_high = confidence_interval(
                score_pairs,
                lambda sample: _mean([strict_value - normal_value for normal_value, strict_value in sample]),
                resamples=resamples, seed=seed + 1,
            )
            enforcement.append({
                "model_family": _model_family(model_key),
                "reasoning_setting": _reasoning_setting(model_key), "condition": condition.value,
                "pairs": len(ids), "normal_games": len(summary_groups[normal]),
                "strict_games": len(summary_groups[strict]),
                "pair_complete": ({row["game_id"] for row in summary_groups[normal]}
                                  == {row["game_id"] for row in summary_groups[strict]}),
                "normal_solve": _mean([normal_solve[i] for i in ids]),
                "strict_solve": _mean([strict_solve[i] for i in ids]), "solve_penalty": solve_penalty,
                "solve_ci_low": solve_low, "solve_ci_high": solve_high,
                "normal_score": _mean([normal_score[i] for i in ids]),
                "strict_score": _mean([strict_score[i] for i in ids]), "score_penalty": score_penalty,
                "score_ci_low": score_low, "score_ci_high": score_high,
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
            validate_pair(named_key, unnamed_key)
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
                              "pairs": len(pairs), "left_games": len(named), "right_games": len(unnamed),
                              "pair_complete": set(named) == set(unnamed),
                              "delta": delta, "ci_low": low, "ci_high": high})

    model_contrasts = []
    for left_model, right_model in (("gpt5", "gpt4o"), ("gpt56", "gpt5"), ("gpt56", "gpt4o")):
        for condition in Condition:
            for mode in GameMode:
                left_key, right_key = ((left_model, condition.value, mode.value),
                                       (right_model, condition.value, mode.value))
                if left_key not in summary_groups or right_key not in summary_groups:
                    continue
                left_ids = {row["game_id"] for row in summary_groups[left_key]}
                right_ids = {row["game_id"] for row in summary_groups[right_key]}
                for offset, metric in enumerate(METRICS):
                    left, right = game_values(left_key, metric), game_values(right_key, metric)
                    ids = sorted(left.keys() & right.keys())
                    pairs = [(left[game_id], right[game_id]) for game_id in ids]
                    low, high = confidence_interval(
                        pairs, lambda sample: _mean([a - b for a, b in sample]),
                        resamples=resamples, seed=seed + offset,
                    )
                    model_contrasts.append({
                        "left_model": left_model, "right_model": right_model,
                        "condition": condition.value, "game_mode": mode.value,
                        "metric": metric, "pairs": len(pairs), "left_games": len(left_ids),
                        "right_games": len(right_ids), "pair_complete": left_ids == right_ids,
                        "delta": _mean([a - b for a, b in pairs]), "ci_low": low, "ci_high": high,
                    })

    dynamic_contrasts = []
    for model, mode in sorted({(key[0], key[2]) for key in summary_groups}):
        historical_key, dynamic_key = ((model, "hist_unnamed", mode),
                                       (model, "dynamic_256", mode))
        if historical_key not in summary_groups or dynamic_key not in summary_groups:
            continue
        for offset, metric in enumerate(METRICS):
            historical = list(game_values(historical_key, metric).values())
            dynamic = list(game_values(dynamic_key, metric).values())
            low, high = independent_difference_interval(
                historical, dynamic, resamples=resamples, seed=seed + offset,
            )
            dynamic_contrasts.append({
                "model_key": model, "game_mode": mode, "metric": metric,
                "historical_games": len(historical), "dynamic_games": len(dynamic),
                "delta_hist_unnamed_minus_dynamic": (
                    mean(historical) - mean(dynamic) if historical and dynamic else None
                ), "ci_low": low, "ci_high": high,
            })

    output.mkdir(parents=True, exist_ok=True)
    for rows in (age_rows, round_rows, contrasts, model_contrasts, dynamic_contrasts,
                 reasoning_effects, enforcement, penalty_reductions):
        for row in rows:
            row["split"] = split
    games, processed_proposals = _processed_rows(summaries, proposals, run_metadata)
    _write_table(metric_rows, output / "metrics", list(metric_rows[0]))
    _write_table(coverage_rows, output / "run_coverage", [
        "run_id", "model_key", "condition", "game_mode", "split", "reasoning_effort",
        "requested", "completed", "pending", "complete", "solved", "recorded_cost_usd",
    ])
    _write_table(age_rows, output / "constraint_age", ["model_key", "condition", "game_mode", "clue_age", "violations", "exposures", "violation_rate"])
    _write_table(round_rows, output / "consistency_by_round", ["model_key", "condition", "game_mode", "decision_round", "consistent", "action_valid", "consistency_rate"])
    _write_table(games, output / "games", list(games[0]) if games else [])
    _write_table(processed_proposals, output / "proposals", list(processed_proposals[0]) if processed_proposals else [])
    _write_table(contrasts, output / "paired_contrasts", [
        "model_key", "game_mode", "contrast", "metric", "pairs", "left_games",
        "right_games", "pair_complete", "delta", "ci_low", "ci_high",
    ])
    _write_table(model_contrasts, output / "model_contrasts", [
        "left_model", "right_model", "condition", "game_mode", "metric", "pairs",
        "left_games", "right_games", "pair_complete", "delta", "ci_low", "ci_high",
    ])
    _write_table(dynamic_contrasts, output / "dynamic_contrasts", [
        "model_key", "game_mode", "metric", "historical_games", "dynamic_games",
        "delta_hist_unnamed_minus_dynamic", "ci_low", "ci_high",
    ])
    _write_table(reasoning_effects, output / "reasoning_effects", [
        "model_family", "condition", "game_mode", "metric", "pairs",
        "baseline_games", "medium_games", "pair_complete",
        "delta_medium_minus_baseline", "ci_low", "ci_high",
    ])
    _write_table(enforcement, output / "enforcement_penalty", [
        "model_family", "reasoning_setting", "condition", "pairs", "normal_games",
        "strict_games", "pair_complete", "normal_solve",
        "strict_solve", "solve_penalty", "solve_ci_low", "solve_ci_high",
        "normal_score", "strict_score", "score_penalty", "score_ci_low", "score_ci_high",
    ])
    _write_table(penalty_reductions, output / "penalty_reduction", [
        "model_family", "condition", "pairs", "baseline_penalty", "medium_penalty",
        "penalty_reduction", "ci_low", "ci_high",
    ])
    for source, target in (
        ("paired_contrasts", "contrasts/paired"), ("model_contrasts", "contrasts/model"),
        ("dynamic_contrasts", "contrasts/dynamic"), ("reasoning_effects", "contrasts/reasoning"),
        ("enforcement_penalty", "contrasts/enforcement_penalty"),
        ("penalty_reduction", "contrasts/penalty_reduction"),
        ("constraint_age", "diagnostics/constraint_age"),
        ("consistency_by_round", "diagnostics/consistency_by_round"),
    ):
        table = pq.read_table(output / f"{source}.parquet")
        target_path = output / f"{target}.parquet"
        target_path.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(table, target_path)
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
    analysis_metadata = {
        "analysis_schema_version": ANALYSIS_SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False,
        ).stdout.strip() or None,
        "bootstrap_resamples": resamples, "bootstrap_seed": seed,
        "provider": provider, "split": split, "model_prefixes": list(model_prefixes),
        "source_run_ids": sorted(row.get("run_id") for row in run_metadata if row.get("run_id")),
        "benchmark_versions": sorted({row.get("benchmark_version") for row in summaries if row.get("benchmark_version")}),
        "prompt_versions": sorted({row.get("prompt_version") for row in summaries if row.get("prompt_version")}),
        "manifest_hashes": sorted({row.get("manifest_hash") for row in summaries if row.get("manifest_hash")}),
        "model_config_hashes": sorted({row.get("model_config_hash") for row in run_metadata if row.get("model_config_hash")}),
        "benchmark_config_hashes": sorted({row.get("benchmark_config_hash") for row in run_metadata if row.get("benchmark_config_hash")}),
        "coverage_complete": all(row["complete"] for row in coverage_rows),
    }
    (output / "analysis_metadata.json").write_text(json.dumps(analysis_metadata, indent=2, sort_keys=True) + "\n")
    validate_analysis_snapshot(output)
