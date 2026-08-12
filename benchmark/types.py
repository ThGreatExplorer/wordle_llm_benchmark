from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol


class Condition(StrEnum):
    HIST_NAMED = "hist_named"
    HIST_UNNAMED = "hist_unnamed"
    DYNAMIC_256 = "dynamic_256"


class Feedback(StrEnum):
    EXACT = "EXACT"
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"


FeedbackPattern = tuple[Feedback, Feedback, Feedback, Feedback, Feedback]


class GuessStatus(StrEnum):
    FORMAT_ERROR = "FORMAT_ERROR"
    LEXICON_ERROR = "LEXICON_ERROR"
    CONSTRAINT_ERROR = "CONSTRAINT_ERROR"
    VALID = "VALID"


class ProposalError(StrEnum):
    PROTOCOL_ERROR = "PROTOCOL_ERROR"


@dataclass(frozen=True)
class HistoryEntry:
    guess: str
    feedback: FeedbackPattern
    decision_round: int


@dataclass(frozen=True)
class GuessEvaluation:
    raw: str
    normalized: str
    status: GuessStatus
    error_subcode: str | None = None
    violated_constraint_ages: tuple[int, ...] = ()
    diagnostics: tuple[str, ...] = ()

    @property
    def valid(self) -> bool:
        return self.status is GuessStatus.VALID


@dataclass(frozen=True)
class ModelResponse:
    raw_text: str
    guesses: list[str] | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    latency_ms: float = 0.0
    provider_request_id: str | None = None
    model_returned: str | None = None
    protocol_error: str | None = None


class ModelAdapter(Protocol):
    async def predict(self, prompt: str) -> ModelResponse: ...


@dataclass
class GameState:
    secret: str
    initial_secrets: tuple[str, ...]
    legal_guesses: tuple[str, ...]
    history: list[HistoryEntry] = field(default_factory=list)

    def accept(self, guess: str, feedback: FeedbackPattern, decision_round: int) -> None:
        self.history.append(HistoryEntry(guess, feedback, decision_round))

    @property
    def solved(self) -> bool:
        return bool(self.history and self.history[-1].guess == self.secret)
