import csv
import json
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from benchmark.analysis import analyze_results


def write(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


def evaluation(action_status: str, consistent: bool | None, ages=()) -> dict:
    return {"raw": "word", "normalized": "word", "action_status": action_status,
            "error_subcode": None, "constraint_consistent": consistent,
            "violated_constraint_ages": list(ages), "diagnostics": []}


def test_analysis_exports_metrics_bootstrap_parquet_and_plots(tmp_path: Path) -> None:
    source, output = tmp_path / "results", tmp_path / "analysis"
    source.mkdir()
    summaries, proposals = [], []
    for condition, solved, score in (("hist_named", True, 2), ("hist_unnamed", False, 7)):
        summaries.append({
            "run_id": "run", "model_key": "model", "condition": condition, "game_id": "hist_0001",
            "game_mode": "normal",
            "solved": solved, "round_score": score, "repair_attempt_count": 1,
            "repair_success_count": int(solved), "forfeit_count": int(not solved),
            "played_guess_count": int(solved),
        })
        proposals.extend([
            {"run_id": "run", "model_key": "model", "condition": condition, "game_id": "hist_0001",
             "decision_round": 1, "proposal_type": "initial",
             "game_mode": "normal",
             "evaluations": [evaluation("VALID", True), evaluation("VALID", True), evaluation("LEXICON_ERROR", None)],
             "information_gain": [1, .8, None], "ig_oracle": 2, "played": True},
            {"run_id": "run", "model_key": "model", "condition": condition, "game_id": "hist_0001",
             "decision_round": 2, "proposal_type": "initial",
             "game_mode": "normal",
             "evaluations": [evaluation("VALID", False, (1,)), evaluation("VALID", True), evaluation("VALID", True)],
             "information_gain": [.2, .5, .4], "ig_oracle": 1, "played": False},
        ])
    write(source / "summaries.jsonl", summaries)
    write(source / "proposals.jsonl", proposals)

    analyze_results(source, output, resamples=100, seed=7)
    metrics = list(csv.DictReader((output / "metrics.csv").open()))
    assert len(metrics) == 2
    assert float(metrics[0]["initial_action_valid_at_1"]) == 1
    assert float(metrics[0]["constraint_consistent_at_1"]) == .5
    assert float(metrics[0]["strict_valid_at_1"]) == .5
    assert float(metrics[0]["ig_efficiency"]) == .35
    assert pq.read_table(output / "metrics.parquet").num_rows == 2
    age = list(csv.DictReader((output / "constraint_age.csv").open()))
    assert age[0]["violations"] == "1" and age[0]["exposures"] == "3"
    contrasts = list(csv.DictReader((output / "paired_contrasts.csv").open()))
    assert any(row["metric"] == "solve_at_6" and float(row["delta"]) == 1 for row in contrasts)
    assert (output / "solve_at_6.svg").read_text().startswith("<svg")
    dashboard = (output / "dashboard.html").read_text()
    assert "Interactive aggregate results" in dashboard
    assert '"hist_named"' in dashboard and "constraint_age" in dashboard


def test_analysis_rejects_duplicate_completed_games(tmp_path: Path) -> None:
    row = {"run_id": "r", "model_key": "m", "condition": "hist_named", "game_mode": "normal", "game_id": "g"}
    write(tmp_path / "summaries.jsonl", [row, row])
    write(tmp_path / "proposals.jsonl", [])
    try:
        analyze_results(tmp_path, tmp_path / "out", resamples=1)
    except ValueError as exc:
        assert "duplicate" in str(exc)
    else:
        raise AssertionError("duplicate games accepted")


def test_protocol_errors_remain_in_validity_denominators() -> None:
    from benchmark.analysis.pipeline import aggregate

    summary = {"game_id": "g", "solved": False, "round_score": 7, "repair_attempt_count": 0,
               "repair_success_count": 0, "forfeit_count": 0, "played_guess_count": 0}
    proposal = {"game_id": "g", "decision_round": 1, "proposal_type": "initial",
                "evaluations": [], "information_gain": [], "ig_oracle": 1}
    metrics = aggregate([summary], [proposal])
    assert metrics["initial_action_valid_at_1"] == 0
    assert metrics["initial_action_valid_at_3"] == 0


def test_analysis_ignores_orphan_proposals(tmp_path: Path) -> None:
    summary = {"run_id": "run", "model_key": "model", "condition": "hist_named",
               "game_mode": "normal", "game_id": "done", "solved": True, "round_score": 1,
               "repair_attempt_count": 0, "repair_success_count": 0, "forfeit_count": 0,
               "played_guess_count": 1}
    base = {"run_id": "run", "model_key": "model", "condition": "hist_named",
            "game_mode": "normal", "decision_round": 1, "proposal_type": "initial",
            "information_gain": [1, 1, 1], "ig_oracle": 1, "played": True,
            "evaluations": [evaluation("VALID", True)] * 3}
    write(tmp_path / "summaries.jsonl", [summary])
    write(tmp_path / "proposals.jsonl", [base | {"game_id": "done"},
                                          base | {"game_id": "orphan", "evaluations": []}])
    analyze_results(tmp_path, tmp_path / "out", resamples=1)
    row = next(csv.DictReader((tmp_path / "out/metrics.csv").open()))
    assert float(row["initial_action_valid_at_1"]) == 1


def test_reasoning_effect_and_enforcement_penalty_are_game_paired(tmp_path: Path) -> None:
    summaries, proposals = [], []
    for model, mode, solved, score, reasoning in (
        ("gpt5", "normal", False, 7, 0), ("gpt5", "strict", False, 7, 0),
        ("gpt5_medium", "normal", True, 3, 30), ("gpt5_medium", "strict", True, 4, 40),
    ):
        common = {"run_id": f"{model}-{mode}", "model_key": model,
                  "condition": "hist_named", "game_mode": mode, "game_id": "hist_0001"}
        summaries.append(common | {
            "solved": solved, "round_score": score, "played_guess_count": 1,
            "repair_attempt_count": 0, "repair_success_count": 0, "forfeit_count": 0,
            "reasoning_tokens_total": reasoning, "latency_ms_total": 100,
            "estimated_cost_usd_total": .01,
        })
        proposals.append(common | {
            "decision_round": 1, "proposal_type": "initial", "played": True,
            "evaluations": [evaluation("VALID", True)] * 3,
            "information_gain": [1, .5, .25], "ig_oracle": 1,
            "reasoning_tokens": reasoning, "latency_ms": 100,
        })
    write(tmp_path / "summaries.jsonl", summaries)
    write(tmp_path / "proposals.jsonl", proposals)
    analyze_results(tmp_path, tmp_path / "out", resamples=20, seed=1)

    effects = list(csv.DictReader((tmp_path / "out/reasoning_effects.csv").open()))
    solve = next(row for row in effects if row["game_mode"] == "normal" and row["metric"] == "solve_at_6")
    assert float(solve["delta_medium_minus_baseline"]) == 1 and solve["pairs"] == "1"
    reduction = next(csv.DictReader((tmp_path / "out/penalty_reduction.csv").open()))
    assert float(reduction["penalty_reduction"]) == 0
    assert len(list(csv.DictReader((tmp_path / "out/gpt5_reasoning_benchmark.csv").open()))) == 4


def test_reasoning_comparison_rejects_unpaired_game_ids(tmp_path: Path) -> None:
    summaries, proposals = [], []
    for model, game_id in (("gpt5", "a"), ("gpt5_medium", "b")):
        common = {"run_id": model, "model_key": model, "condition": "hist_named",
                  "game_mode": "normal", "game_id": game_id}
        summaries.append(common | {"solved": True, "round_score": 1, "played_guess_count": 1,
                                    "repair_attempt_count": 0, "repair_success_count": 0,
                                    "forfeit_count": 0})
        proposals.append(common | {"decision_round": 1, "proposal_type": "initial",
                                   "played": True, "evaluations": [evaluation("VALID", True)] * 3,
                                   "information_gain": [1, 1, 1], "ig_oracle": 1})
    write(tmp_path / "summaries.jsonl", summaries)
    write(tmp_path / "proposals.jsonl", proposals)
    with pytest.raises(ValueError, match="different game IDs"):
        analyze_results(tmp_path, tmp_path / "out", resamples=1)
