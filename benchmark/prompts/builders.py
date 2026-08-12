from __future__ import annotations

from benchmark import PROMPT_VERSION
from benchmark.types import Condition, GameState, GuessStatus

BANNED = ("wordle", "green", "yellow", "gray", "grey", "nyt", "new york times", "hard mode")

_RULES = """Your goal is to identify the secret five-letter English word within at most six decision rounds.

After each accepted guess, you receive exactly one feedback label for each letter:
- EXACT: the letter matches the secret at this exact position.
- PRESENT: the letter occurs in the secret, but not at this position among the still-unmatched letters.
- ABSENT: no unmatched occurrence of this letter remains in the secret.

Duplicate letters are evaluated as follows:
1. Assign all EXACT matches first.
2. For the remaining positions, assign PRESENT only while an unmatched occurrence of that letter remains in the secret.
3. Otherwise assign ABSENT.

STRICT CONSISTENCY RULE"""

_CONSISTENCY = """To check whether a proposed word is consistent, temporarily treat that proposed word as if it were the secret. Re-evaluate each previous accepted guess against that proposed word using the feedback rules above.

For every previous accepted row, the five feedback labels produced in this check must exactly match the five recorded feedback labels for that row.

If even one label differs for any previous row, the proposed word is invalid.

You must check every previous accepted row, not only the most recent one.

Only your first-ranked guess will actually be played. The second and third guesses are alternate recommendations, but they must also be valid under all of the same rules.

Before answering, silently verify each of your three proposed guesses against every previous accepted feedback row.

Return exactly one JSON object with exactly one field named "guesses". Its value must be an array of exactly three guess strings ranked from best to worst.

Do not include explanations, reasoning, or any other fields."""

_DYNAMIC = """CANDIDATE SET

For this game, the secret was selected uniformly from exactly the 256 candidate words listed below.

These 256 words are also the complete legal guess set for this game.

Every one of the three guesses you return must:
1. appear exactly in the candidate list below; and
2. satisfy the strict consistency rule for every previous accepted feedback row.

A word that satisfies the feedback constraints but is not in the candidate list is invalid."""


def instructional_prose(condition: Condition) -> str:
    named = condition is Condition.HIST_NAMED
    intro = (
        "You are playing Wordle under a strict consistency rule."
        if named else
        "You are solving a five-letter word deduction game under a strict consistency rule."
    )
    legal = (
        "Every one of the three guesses you return must be a legal five-letter Wordle guess"
        if named else
        "Every one of the three guesses you return must be a legal five-letter English guess for this game"
    )
    parts = [intro, _RULES,
             f"{legal} and must independently satisfy every previous accepted feedback row.",
             _CONSISTENCY]
    if condition is Condition.DYNAMIC_256:
        parts.append(_DYNAMIC)
    return "\n\n".join(parts)


def _repair(
    condition: Condition, rejected_guess: str | None, rejection: GuessStatus | str
) -> str:
    error = rejection.value if isinstance(rejection, GuessStatus) else rejection
    if error == "PROTOCOL_ERROR":
        return """REPAIR REQUEST

Your previous response was rejected with PROTOCOL_ERROR.

The response did not satisfy the required output structure of exactly three guess strings in the required JSON object.

Re-evaluate the complete game state and return a new response satisfying the output contract and all game rules above."""

    prefix = f'''REPAIR REQUEST

Your previous first-ranked proposal "{rejected_guess}" was rejected with {error}.
'''
    if error == "CONSTRAINT_ERROR":
        detail = """This means that the proposed word failed the strict consistency test above for at least one previous accepted feedback row: if the proposed word is treated as the secret, at least one previous guess would not reproduce its recorded five feedback labels exactly.

The specific violated row is not provided.

Re-check every previous accepted feedback row before answering."""
    elif error == "LEXICON_ERROR" and condition is Condition.DYNAMIC_256:
        detail = """This means that the proposed word was not one of the 256 candidate words listed above.

Re-evaluate the complete game state."""
    elif error == "LEXICON_ERROR":
        detail = """This means that the proposed word was not a legal five-letter guess for this game.

Re-evaluate the complete game state."""
    elif error == "FORMAT_ERROR":
        detail = """This means that it was not exactly five ASCII alphabetic letters.

Re-evaluate the complete game state."""
    else:
        raise ValueError(f"unknown repair error: {error}")
    return f"{prefix}\n{detail}\n\nReturn exactly three new ranked guesses satisfying all rules above."


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
            "Candidate words, in fixed order:\n\n" + " ".join(state.initial_secrets)
        )
    history = "\n\n".join(
        f"Row {index}\nGuess: {entry.guess}\nFeedback: {' '.join(item.value for item in entry.feedback)}"
        for index, entry in enumerate(state.history, 1)
    ) or "(none)"
    parts.extend([
        f"Accepted feedback history:\n\n{history}",
        f"Current decision round: {decision_round} of 6",
    ])
    if rejection is not None:
        parts.append(_repair(condition, rejected_guess, rejection))
    return "\n\n".join(parts)
