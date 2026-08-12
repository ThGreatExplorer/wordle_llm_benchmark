import asyncio
import json

from benchmark.engine.validator import filter_candidates
from benchmark.experiment import runner
from benchmark.experiment.runner import append_result, run_game
from benchmark.providers.mock import MockAdapter, parse_top_three
from benchmark.engine.feedback import score
from benchmark.types import Condition, GameMode, GameState, HistoryEntry, ModelResponse


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
        game_mode=GameMode.STRICT,
    ))
    assert "PROTOCOL_ERROR" in adapter.prompts[1] and "<unavailable>" not in adapter.prompts[1]
    assert result.summary.protocol_error_count == 1
    assert result.summary.format_error_count == 1
    assert result.summary.lexicon_error_count == 1
    assert result.summary.all_suggestion_constraint_violation_count >= 1


def test_repair_forfeit_and_session_isolation() -> None:
    adapter = MockAdapter([
        ["xxxxxx", "trace", "crane"], ["zzzzz", "trace", "crane"],
        ["crane", "trace", "slate"], ["slate", "trace", "crane"],
    ])
    state = GameState("slate", ("crane", "slate", "trace"), ("crane", "slate", "trace"))
    result = asyncio.run(run_game(adapter, Condition.HIST_UNNAMED, state, game_mode=GameMode.STRICT))
    assert result.summary.solved and result.summary.solve_round == 3
    assert result.summary.forfeit_count == result.summary.repair_attempt_count == 1
    assert len(result.state.history) == 2
    assert "xxxxxx" in adapter.prompts[1] and "FORMAT_ERROR" in adapter.prompts[1]
    assert "xxxxxx" not in adapter.prompts[2] and "zzzzz" not in adapter.prompts[2]
    assert "Guess: crane" in adapter.prompts[3]


def test_valid_repair_and_six_round_loss(tmp_path) -> None:
    repaired = MockAdapter([["xxxxx", "crane", "trace"], ["slate", "crane", "trace"]])
    result = asyncio.run(run_game(repaired, Condition.HIST_NAMED,
                                  GameState("slate", ("slate", "crane"), ("slate", "crane")),
                                  game_mode=GameMode.STRICT))
    assert result.summary.solved and result.summary.repair_success_count == 1

    losing = MockAdapter([["xxxxx", "crane", "trace"]] * 12)
    result = asyncio.run(run_game(losing, Condition.HIST_NAMED,
                                  GameState("slate", ("slate", "crane"), ("slate", "crane")),
                                  game_mode=GameMode.STRICT))
    assert not result.summary.solved and result.summary.round_score == 7
    assert result.summary.played_guess_count == 0 and result.summary.forfeit_count == 6
    assert result.summary.lexicon_error_count == 24
    proposal_path, summary_path = tmp_path / "proposals.jsonl", tmp_path / "summaries.jsonl"
    append_result(proposal_path, summary_path, result, {"run_id": "test", "game_id": "game"})
    assert len(proposal_path.read_text().splitlines()) == 12
    assert json.loads(summary_path.read_text())["forfeit_count"] == 6


def test_same_constraint_violation_plays_normal_and_forfeits_strict() -> None:
    history = [HistoryEntry("crane", score("slate", "crane"), 1)]
    normal_state = GameState("slate", ("slate", "crane", "trace"), ("slate", "crane", "trace"), history.copy())
    strict_state = GameState("slate", ("slate", "crane", "trace"), ("slate", "crane", "trace"), history.copy())
    responses = [["crane", "slate", "trace"]] * 12

    normal = asyncio.run(run_game(MockAdapter(responses), Condition.HIST_NAMED, normal_state,
                                  game_mode=GameMode.NORMAL))
    strict_adapter = MockAdapter(responses)
    strict = asyncio.run(run_game(strict_adapter, Condition.HIST_NAMED, strict_state,
                                  game_mode=GameMode.STRICT))

    assert normal.proposals[0].evaluations[0].constraint_consistent is False
    assert normal.proposals[0].played and normal.proposals[0].information_gain[0] is not None
    assert normal.proposals[0].feedback is not None
    assert normal.proposals[0].candidate_count_after == len(filter_candidates(
        normal.state.initial_secrets, normal.state.history[:2]
    ))
    assert normal.summary.repair_attempt_count == 0
    assert normal.summary.constraint_inconsistent_played_guess_count == 6
    assert normal.summary.repeat_played_guess_count == 6
    assert len(normal.state.history) == 7
    assert strict.proposals[0].evaluations[0].constraint_consistent is False
    assert strict.proposals[0].information_gain[0] is None
    assert strict.summary.forfeit_count == strict.summary.repair_attempt_count == 6
    assert len(strict.state.history) == 1
    assert "CONSTRAINT_ERROR" in strict_adapter.prompts[1]
    assert normal.proposals[0].ig_oracle_kind == "legal"
    assert strict.proposals[0].ig_oracle_kind == "strict"


def test_consistent_and_action_invalid_guesses_share_mode_independent_behavior() -> None:
    for mode in GameMode:
        solved = asyncio.run(run_game(
            MockAdapter([["slate", "crane", "trace"]]), Condition.HIST_NAMED,
            GameState("slate", ("slate", "crane", "trace"), ("slate", "crane", "trace")),
            game_mode=mode,
        ))
        assert solved.summary.solved and solved.summary.repair_attempt_count == 0

        repaired = asyncio.run(run_game(
            MockAdapter([["xxxxxx", "slate", "crane"], ["slate", "crane", "trace"]]),
            Condition.HIST_NAMED,
            GameState("slate", ("slate", "crane", "trace"), ("slate", "crane", "trace")),
            game_mode=mode,
        ))
        assert repaired.summary.solved and repaired.summary.repair_success_count == 1


def test_information_oracle_universe_depends_on_mode(monkeypatch) -> None:
    history = [HistoryEntry("crane", score("slate", "crane"), 1)]
    state = GameState("slate", ("slate", "trace"), ("slate", "trace", "crane"), history)
    feasible = filter_candidates(state.initial_secrets, history)
    universes = []
    monkeypatch.setattr(runner, "best_information_gain",
                        lambda guesses, secrets: universes.append(tuple(guesses)) or 0.0)
    response = ModelResponse(raw_text="{}", guesses=[])

    runner._record(response, (), "prompt", "initial", 2, state, feasible, 0, 0, 0,
                   GameMode.NORMAL)
    runner._record(response, (), "prompt", "initial", 2, state, feasible, 0, 0, 0,
                   GameMode.STRICT)

    assert universes[0] == state.legal_guesses
    assert universes[1] == filter_candidates(state.legal_guesses, history)
