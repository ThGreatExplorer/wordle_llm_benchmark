import asyncio
import json

from benchmark.experiment.runner import append_result, run_game
from benchmark.providers.mock import MockAdapter, parse_top_three
from benchmark.types import Condition, GameState


def test_parser_preserves_strings_and_rejects_bad_protocol() -> None:
    assert parse_top_three('{"guesses":[" CRANE ","slate","trace"]}') == [" CRANE ", "slate", "trace"]
    assert parse_top_three('{"guesses":["crane"]}') is None
    assert parse_top_three("not json") is None


def test_summary_logs_protocol_and_each_guess_error_class() -> None:
    adapter = MockAdapter([
        "not json", ["xxxxxx", "zzzzz", "crane"],
        ["crane", "other", "trace"], ["slate", "crane", "trace"],
    ])
    result = asyncio.run(run_game(
        adapter, Condition.HIST_NAMED,
        GameState("slate", ("slate", "crane", "trace"), ("slate", "crane", "trace", "other")),
    ))
    assert result.summary.protocol_error_count == 1
    assert result.summary.format_error_count == 1
    assert result.summary.lexicon_error_count == 1
    assert result.summary.constraint_error_count >= 1


def test_repair_forfeit_and_session_isolation() -> None:
    adapter = MockAdapter([
        ["xxxxxx", "trace", "crane"], ["zzzzz", "trace", "crane"],
        ["crane", "trace", "slate"], ["slate", "trace", "crane"],
    ])
    state = GameState("slate", ("crane", "slate", "trace"), ("crane", "slate", "trace"))
    result = asyncio.run(run_game(adapter, Condition.HIST_UNNAMED, state))
    assert result.summary.solved and result.summary.solve_round == 3
    assert result.summary.forfeit_count == result.summary.repair_attempt_count == 1
    assert len(result.state.history) == 2
    assert "xxxxxx" in adapter.prompts[1] and "FORMAT_ERROR" in adapter.prompts[1]
    assert "xxxxxx" not in adapter.prompts[2] and "zzzzz" not in adapter.prompts[2]
    assert "crane:" in adapter.prompts[3]


def test_valid_repair_and_six_round_loss(tmp_path) -> None:
    repaired = MockAdapter([["xxxxx", "crane", "trace"], ["slate", "crane", "trace"]])
    result = asyncio.run(run_game(repaired, Condition.HIST_NAMED,
                                  GameState("slate", ("slate", "crane"), ("slate", "crane"))))
    assert result.summary.solved and result.summary.repair_success_count == 1

    losing = MockAdapter([["xxxxx", "crane", "trace"]] * 12)
    result = asyncio.run(run_game(losing, Condition.HIST_NAMED,
                                  GameState("slate", ("slate", "crane"), ("slate", "crane"))))
    assert not result.summary.solved and result.summary.round_score == 7
    assert result.summary.accepted_guess_count == 0 and result.summary.forfeit_count == 6
    assert result.summary.lexicon_error_count == 24
    proposal_path, summary_path = tmp_path / "proposals.jsonl", tmp_path / "summaries.jsonl"
    append_result(proposal_path, summary_path, result, {"run_id": "test", "game_id": "game"})
    assert len(proposal_path.read_text().splitlines()) == 12
    assert json.loads(summary_path.read_text())["forfeit_count"] == 6
