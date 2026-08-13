import json
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from benchmark.analysis import analyze_results
from dashboard.content import load_content, metric_help
from dashboard.data import filter_games, filter_metrics, load_game_proposals, validate_snapshot
from dashboard.views.game_explorer import _played_rows, _round_states, wordle_row


def _evaluation() -> dict:
    return {"raw": "slate", "normalized": "slate", "action_status": "VALID",
            "error_subcode": None, "constraint_consistent": True,
            "violated_constraint_ages": [], "diagnostics": []}


@pytest.fixture
def analysis_dir(tmp_path: Path) -> Path:
    source, output = tmp_path / "results", tmp_path / "analysis"
    run = source / "gpt5-eval"
    run.mkdir(parents=True)
    metadata = {"run_id": "gpt5-eval", "provider": "openai", "split": "eval",
                "model_key": "gpt5", "condition": "hist_named", "game_mode": "normal",
                "reasoning_effort": "minimal", "requested_games": 1}
    (run / "metadata.json").write_text(json.dumps(metadata))
    summary = metadata | {"game_id": "game-1", "solved": True, "solve_round": 1,
                          "round_score": 1, "played_guess_count": 1,
                          "initial_action_invalid_count": 0, "initial_constraint_violation_count": 0,
                          "constraint_consistent_played_guess_count": 1,
                          "constraint_inconsistent_played_guess_count": 0,
                          "repair_attempt_count": 0, "repair_success_count": 0, "forfeit_count": 0,
                          "input_tokens_total": 10, "output_tokens_total": 5,
                          "reasoning_tokens_total": 0, "latency_ms_total": 100,
                          "estimated_cost_usd_total": .01}
    proposal = metadata | {"game_id": "game-1", "decision_round": 1,
                           "proposal_type": "initial", "played": True, "played_guess": "slate",
                           "feedback": ["EXACT"] * 5, "candidate_count_before": 2315,
                           "candidate_count_after": 1, "evaluations": [_evaluation()] * 3,
                           "information_gain": [5.0, 4.0, 3.0], "ig_oracle": 5.0,
                           "ig_oracle_kind": "legal", "input_tokens": 10, "output_tokens": 5,
                           "reasoning_tokens": 0, "latency_ms": 100,
                           "estimated_cost_usd": .01}
    (run / "summaries.jsonl").write_text(json.dumps(summary) + "\n")
    (run / "proposals.jsonl").write_text(json.dumps(proposal) + "\n")
    analyze_results(source, output, provider="openai", split="eval", resamples=2)
    return output


def test_duckdb_loading_filtering_and_trajectory(analysis_dir: Path) -> None:
    metrics = filter_metrics(analysis_dir, {"model_key": ["gpt5"]})
    games = filter_games(analysis_dir, {"condition": ["hist_named"], "solved": True})
    trajectory = load_game_proposals(analysis_dir, "gpt5-eval", "game-1")
    assert len(metrics) == len(games) == len(trajectory) == 1
    assert metrics.iloc[0]["solve_at_6"] == 1
    assert trajectory.iloc[0]["top1"] == "slate" and trajectory.iloc[0]["top1_played"]
    assert pd.read_parquet(analysis_dir / "games.parquet").shape[0] == len(games)


def test_content_lookup_and_snapshot_validation(analysis_dir: Path) -> None:
    assert metric_help("constraint_consistent_at_1")["direction"] == "higher"
    assert load_content("findings")[0]["evidence"]["table"] == "enforcement"
    assert validate_snapshot(analysis_dir) == []


def test_required_column_validation(tmp_path: Path) -> None:
    analysis = tmp_path / "analysis"
    analysis.mkdir()
    (analysis / "analysis_metadata.json").write_text('{"analysis_schema_version":"analysis-v1"}')
    pd.DataFrame({"wrong": [1]}).to_parquet(analysis / "metrics.parquet")
    with pytest.raises(ValueError, match="missing columns"):
        filter_metrics(analysis, {})


def test_report_renders_without_optional_reasoning_runs(analysis_dir: Path, monkeypatch) -> None:
    monkeypatch.setenv("WORDLE_ANALYSIS_DIR", str(analysis_dir))
    app = AppTest.from_file("dashboard/app.py").run(timeout=20)
    assert not app.exception
    assert app.title[0].value == "Wordle LLM Benchmark"
    assert any("provisional" not in warning.value.lower() for warning in app.warning) or not app.warning


def test_game_explorer_renders_visual_replay(analysis_dir: Path, monkeypatch) -> None:
    monkeypatch.setenv("WORDLE_ANALYSIS_DIR", str(analysis_dir))
    app = AppTest.from_file("dashboard/app.py").run(timeout=20)
    app.radio[0].set_value("Game Explorer").run(timeout=20)
    assert not app.exception
    assert app.title[0].value == "Game Explorer"
    assert any(metric.label == "Oracle gain" for metric in app.metric)
    assert next(metric.value for metric in app.metric if metric.label == "Secret") != "•••••"
    assert not app.toggle


def test_dashboard_package_has_no_provider_imports() -> None:
    source = "\n".join(path.read_text() for path in Path("dashboard").rglob("*.py"))
    assert "benchmark.providers" not in source and "AsyncOpenAI" not in source


def test_wordle_replay_tiles_and_round_selection(analysis_dir: Path) -> None:
    trajectory = load_game_proposals(analysis_dir, "gpt5-eval", "game-1")
    markup = wordle_row("slate", ["EXACT", "PRESENT", "ABSENT", "EXACT", "PRESENT"])
    assert markup.count("<span") == 5 and "S" in markup and "#538d4e" in markup
    assert _played_rows(trajectory, 1)["played_guess"].tolist() == ["slate"]
    assert [(round_number, status) for round_number, _, status in _round_states(trajectory, 1)] == [(1, "played")]


def test_round_states_show_repaired_and_forfeited_rounds() -> None:
    trajectory = pd.DataFrame([
        {"decision_round": 1, "proposal_type": "initial", "top1_played": False, "top1": "wrong"},
        {"decision_round": 1, "proposal_type": "repair", "top1_played": True, "top1": "slate",
         "played_guess": "slate", "feedback": ["ABSENT"] * 5},
        {"decision_round": 2, "proposal_type": "initial", "top1_played": False, "top1": "xxxxx"},
    ])
    states = _round_states(trajectory, 2)
    assert [(round_number, row.top1, status) for round_number, row, status in states] == [
        (1, "slate", "played after repair"), (2, "xxxxx", "forfeited"),
    ]
