from __future__ import annotations

from benchmark import PROMPT_VERSION
from benchmark.types import Condition, GameState, GuessStatus

BANNED = ("wordle", "green", "yellow", "gray", "grey", "nyt", "new york times", "hard mode")

_FEEDBACK = """The secret is a five-letter English word.

After each accepted guess, you receive one label for each letter:
- EXACT: the letter is in the secret at this exact position.
- PRESENT: the letter occurs in the secret, but not at this position among the still-unmatched letters.
- ABSENT: no unmatched occurrence of this letter remains in the secret."""

_OUTPUT = """Return exactly three ranked next guesses, from best to worst, using this JSON format:
{"guesses":["crane","slate","trace"]}
Do not include explanation."""


def build_prompt(
    condition: Condition,
    state: GameState,
    decision_round: int,
    rejected_guess: str | None = None,
    rejection: GuessStatus | str | None = None,
) -> str:
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
    parts = [f"Prompt version: {PROMPT_VERSION}", intro, _FEEDBACK,
             f"{legal} and must be fully consistent with all feedback from every previous accepted guess."]
    if condition is Condition.DYNAMIC_256:
        if len(state.initial_secrets) != 256 or len(set(state.initial_secrets)) != 256:
            raise ValueError("dynamic condition requires exactly 256 unique candidate words")
        parts.append(
            "For this game, the secret was selected uniformly from exactly the 256 candidate words listed below.\n"
            "Every guess must be one of these 256 words and fully consistent with all previous feedback.\n"
            "Candidate words, in fixed order:\n" + " ".join(state.initial_secrets)
        )
    def visible(word: str) -> str:
        return " ".join(word) if not named and any(term in word.lower() for term in BANNED) else word

    history = "\n".join(
        f"{visible(entry.guess)}: {' '.join(item.value for item in entry.feedback)}" for entry in state.history
    ) or "(none)"
    parts.extend([f"Accepted history:\n{history}", f"Current decision round: {decision_round}"])
    if rejected_guess is not None:
        error = rejection.value if isinstance(rejection, GuessStatus) else rejection
        parts.append(
            f'Your previous first-ranked proposal "{visible(rejected_guess)}" was rejected with {error}. '
            "Re-evaluate the complete game state and return three new guesses."
        )
    parts.append(_OUTPUT)
    prompt = "\n\n".join(parts)
    if not named and any(term in prompt.lower() for term in BANNED):
        raise ValueError("unnamed prompt contains a banned task-identifying term")
    return prompt
