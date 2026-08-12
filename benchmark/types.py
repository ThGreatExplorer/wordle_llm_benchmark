from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol


class Condition(StrEnum):
    HIST_NAMED = "hist_named"
    HIST_UNNAMED = "hist_unnamed"
    DYNAMIC_256 = "dynamic_256"


class GameMode(StrEnum):
    NORMAL = "normal"
    STRICT = "strict"


class Feedback(StrEnum):
    EXACT = "EXACT"
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"


FeedbackPattern = tuple[Feedback, Feedback, Feedback, Feedback, Feedback]


class ActionStatus(StrEnum):
    FORMAT_ERROR = "FORMAT_ERROR"
    LEXICON_ERROR = "LEXICON_ERROR"
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
    action_status: ActionStatus
    error_subcode: str | None = None
    constraint_consistent: bool | None = None
    violated_constraint_ages: tuple[int, ...] = ()
    diagnostics: tuple[str, ...] = ()

    @property
    def action_valid(self) -> bool:
        return self.action_status is ActionStatus.VALID

    @property
    def strict_valid(self) -> bool:
        return self.action_valid and self.constraint_consistent is True


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
    provider_returned: str | None = None
    provider_metadata: dict | None = None
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
