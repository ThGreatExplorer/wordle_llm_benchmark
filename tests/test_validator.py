from benchmark.engine.feedback import score
from benchmark.engine.validator import filter_candidates, is_consistent, validate_guess
from benchmark.types import ActionStatus, Condition, HistoryEntry


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
    assert validate_guess(" six ", legal, [], Condition.HIST_NAMED, 1).action_status is ActionStatus.FORMAT_ERROR
    result = validate_guess("other", legal, [], Condition.DYNAMIC_256, 1)
    assert result.action_status is ActionStatus.LEXICON_ERROR
    assert result.constraint_consistent is None
    assert result.error_subcode == "OUTSIDE_DYNAMIC_POOL"


def test_non_answer_legal_guess_and_repeat_are_valid() -> None:
    history = [HistoryEntry("crane", score("slate", "crane"), 1)]
    evaluation = validate_guess("slate", {"slate"}, history, Condition.HIST_NAMED, 2)
    assert evaluation.action_valid and evaluation.constraint_consistent
    repeated = validate_guess("crane", {"crane"}, [], Condition.HIST_NAMED, 2)
    assert repeated.action_valid and repeated.constraint_consistent


def test_action_validity_is_independent_from_constraint_consistency() -> None:
    history = [
        HistoryEntry("crane", score("blush", "crane"), 1),
        HistoryEntry("plumb", score("blush", "plumb"), 3),
    ]
    result = validate_guess("slate", {"slate"}, history, Condition.HIST_UNNAMED, 4)
    assert result.action_status is ActionStatus.VALID
    assert result.action_valid and result.constraint_consistent is False
    assert result.violated_constraint_ages
