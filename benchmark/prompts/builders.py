from __future__ import annotations

from benchmark import PROMPT_VERSION
from benchmark.types import Condition, GameState, GuessStatus

BANNED = ("wordle", "green", "yellow", "gray", "grey", "nyt", "new york times", "hard mode")

_FEEDBACK = """The secret is a five-letter English word.

After each accepted guess, you receive one label for each letter:
- EXACT: the letter is in the secret at this exact position.
- PRESENT: the letter occurs in the secret, but not at this position among the still-unmatched letters.
- ABSENT: no unmatched occurrence of this letter remains in the secret."""

_OUTPUT = """Return exactly one JSON object with one field named "guesses" whose value is an array of exactly three ranked guess strings, best to worst. Do not include explanation or any other fields."""


def instructional_prose(condition: Condition) -> str:
    named = condition is Condition.HIST_NAMED
    intro = (
        "You are playing Wordle under a strict hard-mode rule."
        if named else
        "You are playing a five-letter word deduction game under a strict consistency rule."
    )
    legal = (
        "Every new guess must be a legal five-letter Wordle guess"
        if named else
        "Every new guess must be a legal five-letter English guess for this game"
    )
    parts = [intro, _FEEDBACK,
             f"{legal} and must be fully consistent with all feedback from every previous accepted guess."]
    if condition is Condition.DYNAMIC_256:
        parts.append(
            "For this game, the secret was selected uniformly from exactly the 256 candidate words listed below.\n"
            "Every guess must be one of these 256 words and fully consistent with all previous feedback."
        )
    parts.append(_OUTPUT)
    return "\n\n".join(parts)


def build_prompt(
    condition: Condition,
    state: GameState,
    decision_round: int,
    rejected_guess: str | None = None,
    rejection: GuessStatus | str | None = None,
) -> str:
    parts = [f"Prompt version: {PROMPT_VERSION}", instructional_prose(condition)]
    if condition is Condition.DYNAMIC_256:
        if len(state.initial_secrets) != 256 or len(set(state.initial_secrets)) != 256:
            raise ValueError("dynamic condition requires exactly 256 unique candidate words")
        parts.append(
            "Candidate words, in fixed order:\n" + " ".join(state.initial_secrets)
        )
    history = "\n".join(
        f"{entry.guess}: {' '.join(item.value for item in entry.feedback)}" for entry in state.history
    ) or "(none)"
    parts.extend([f"Accepted history:\n{history}", f"Current decision round: {decision_round}"])
    if rejected_guess is not None:
        error = rejection.value if isinstance(rejection, GuessStatus) else rejection
        parts.append(
            f'Your previous first-ranked proposal "{rejected_guess}" was rejected with {error}. '
            "Re-evaluate the complete game state and return three new guesses."
        )
    return "\n\n".join(parts)
