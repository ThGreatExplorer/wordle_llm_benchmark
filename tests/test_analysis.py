import csv
import json
from pathlib import Path

import pyarrow.parquet as pq

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
    row = {"model_key": "m", "condition": "hist_named", "game_mode": "normal", "game_id": "g"}
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
