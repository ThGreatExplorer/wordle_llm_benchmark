import csv
import json
from pathlib import Path

import pyarrow.parquet as pq

from benchmark.analysis import analyze_results


def write(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


def evaluation(status: str, gain: float | None, ages=()) -> dict:
    return {"raw": "word", "normalized": "word", "status": status, "error_subcode": None,
            "violated_constraint_ages": list(ages), "diagnostics": []}


def test_analysis_exports_metrics_bootstrap_parquet_and_plots(tmp_path: Path) -> None:
    source, output = tmp_path / "results", tmp_path / "analysis"
    source.mkdir()
    summaries, proposals = [], []
    for condition, solved, score in (("hist_named", True, 2), ("hist_unnamed", False, 7)):
        summaries.append({
            "run_id": "run", "model_key": "model", "condition": condition, "game_id": "hist_0001",
            "solved": solved, "round_score": score, "repair_attempt_count": 1,
            "repair_success_count": int(solved), "forfeit_count": int(not solved),
        })
        proposals.extend([
            {"run_id": "run", "model_key": "model", "condition": condition, "game_id": "hist_0001",
             "decision_round": 1, "proposal_type": "initial",
             "evaluations": [evaluation("VALID", 1), evaluation("VALID", .8), evaluation("LEXICON_ERROR", None)],
             "information_gain": [1, .8, None], "ig_star": 2, "accepted_guess": "crane"},
            {"run_id": "run", "model_key": "model", "condition": condition, "game_id": "hist_0001",
             "decision_round": 2, "proposal_type": "initial",
             "evaluations": [evaluation("CONSTRAINT_ERROR", None, (1,)), evaluation("VALID", .5), evaluation("VALID", .4)],
             "information_gain": [None, .5, .4], "ig_star": 1, "accepted_guess": None},
        ])
    write(source / "summaries.jsonl", summaries)
    write(source / "proposals.jsonl", proposals)

    analyze_results(source, output, resamples=100, seed=7)
    metrics = list(csv.DictReader((output / "metrics.csv").open()))
    assert len(metrics) == 2
    assert float(metrics[0]["initial_valid_at_1"]) == .5
    assert float(metrics[0]["initial_valid_at_3"]) == 4 / 6
    assert float(metrics[0]["ig_efficiency"]) == .5
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
    row = {"model_key": "m", "condition": "hist_named", "game_id": "g"}
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
               "repair_success_count": 0, "forfeit_count": 0}
    proposal = {"game_id": "g", "decision_round": 1, "proposal_type": "initial",
                "evaluations": [], "information_gain": [], "ig_star": 1}
    metrics = aggregate([summary], [proposal])
    assert metrics["initial_valid_at_1"] == 0
    assert metrics["initial_valid_at_3"] == 0
