from collections.abc import Iterable, Sequence

from benchmark.engine.feedback import score
from benchmark.types import ActionStatus, Condition, GuessEvaluation, HistoryEntry


def is_consistent(candidate: str, history: Sequence[HistoryEntry]) -> bool:
    return all(score(candidate, entry.guess) == entry.feedback for entry in history)


def filter_candidates(candidates: Iterable[str], history: Sequence[HistoryEntry]) -> tuple[str, ...]:
    return tuple(candidate for candidate in candidates if is_consistent(candidate, history))


def validate_guess(
    raw_guess: str,
    legal_guesses: set[str] | frozenset[str],
    history: Sequence[HistoryEntry],
    condition: Condition,
    decision_round: int,
) -> GuessEvaluation:
    normalized = raw_guess.strip().lower()
    if len(normalized) != 5 or not normalized.isascii() or not normalized.isalpha():
        return GuessEvaluation(raw_guess, normalized, ActionStatus.FORMAT_ERROR)
    if normalized not in legal_guesses:
        subcode = "OUTSIDE_DYNAMIC_POOL" if condition is Condition.DYNAMIC_256 else None
        return GuessEvaluation(raw_guess, normalized, ActionStatus.LEXICON_ERROR, subcode)

    violated = tuple(
        decision_round - entry.decision_round
        for entry in history
        if score(normalized, entry.guess) != entry.feedback
    )
    diagnostics = ("REPEAT_ACCEPTED_GUESS",) if any(normalized == e.guess for e in history) else ()
    return GuessEvaluation(
        raw_guess, normalized, ActionStatus.VALID,
        constraint_consistent=not violated,
        violated_constraint_ages=violated,
        diagnostics=diagnostics,
    )
