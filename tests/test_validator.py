from benchmark.engine.feedback import score
from benchmark.engine.validator import filter_candidates, is_consistent, validate_guess
from benchmark.types import Condition, GuessStatus, HistoryEntry


def test_consistency_uses_complete_history() -> None:
    history = [
        HistoryEntry("crane", score("blush", "crane"), 1),
        HistoryEntry("plumb", score("blush", "plumb"), 2),
    ]
    assert is_consistent("blush", history)
    assert not is_consistent("plush", history)
    assert filter_candidates(("blush", "plush"), history) == ("blush",)


def test_validation_precedence_and_dynamic_subcode() -> None:
    legal = {"crane", "slate"}
    assert validate_guess(" six ", legal, [], Condition.HIST_NAMED, 1).status is GuessStatus.FORMAT_ERROR
    result = validate_guess("other", legal, [], Condition.DYNAMIC_256, 1)
    assert result.status is GuessStatus.LEXICON_ERROR
    assert result.error_subcode == "OUTSIDE_DYNAMIC_POOL"


def test_non_answer_legal_guess_and_repeat_are_valid() -> None:
    history = [HistoryEntry("crane", score("slate", "crane"), 1)]
    evaluation = validate_guess("slate", {"slate"}, history, Condition.HIST_NAMED, 2)
    assert evaluation.valid
    repeated = validate_guess("crane", {"crane"}, [], Condition.HIST_NAMED, 2)
    assert repeated.valid


def test_constraint_error_reports_all_clue_ages() -> None:
    history = [
        HistoryEntry("crane", score("blush", "crane"), 1),
        HistoryEntry("plumb", score("blush", "plumb"), 3),
    ]
    result = validate_guess("slate", {"slate"}, history, Condition.HIST_UNNAMED, 4)
    assert result.status is GuessStatus.CONSTRAINT_ERROR
    assert result.violated_constraint_ages

