from __future__ import annotations

import json
import hashlib
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from benchmark.engine.feedback import score
from benchmark.engine.information import best_information_gain, information_gain
from benchmark.engine.validator import filter_candidates, validate_guess
from benchmark.prompts import build_prompt
from benchmark.types import Condition, GameState, GuessEvaluation, GuessStatus, ModelAdapter, ModelResponse


@dataclass(frozen=True)
class ProposalRecord:
    decision_round: int
    proposal_type: str
    raw_response: str
    evaluations: tuple[GuessEvaluation, ...]
    protocol_error: str | None
    prompt_hash: str
    candidate_count_before: int
    information_gain: tuple[float | None, ...]
    ig_star: float
    accepted_guess: str | None = None
    feedback: tuple[str, ...] | None = None
    candidate_count_after: int | None = None


@dataclass(frozen=True)
class GameSummary:
    solved: bool
    solve_round: int | None
    round_score: int
    accepted_guess_count: int
    initial_invalid_count: int
    repair_attempt_count: int
    repair_success_count: int
    forfeit_count: int


@dataclass(frozen=True)
class GameResult:
    proposals: tuple[ProposalRecord, ...]
    summary: GameSummary
    state: GameState


def append_result(
    proposal_path: Path, summary_path: Path, result: GameResult, metadata: dict[str, str]
) -> None:
    with proposal_path.open("a") as proposals:
        for proposal in result.proposals:
            proposals.write(json.dumps(metadata | asdict(proposal), separators=(",", ":")) + "\n")
    with summary_path.open("a") as summaries:
        summaries.write(json.dumps(metadata | asdict(result.summary), separators=(",", ":")) + "\n")


def _evaluate(
    response: ModelResponse, state: GameState, condition: Condition, decision_round: int
) -> tuple[GuessEvaluation, ...]:
    if response.guesses is None:
        return ()
    legal = frozenset(state.legal_guesses)
    evaluations = tuple(validate_guess(guess, legal, state.history, condition, decision_round) for guess in response.guesses)
    if len({evaluation.normalized for evaluation in evaluations}) < 3:
        evaluations = tuple(
            GuessEvaluation(
                evaluation.raw, evaluation.normalized, evaluation.status, evaluation.error_subcode,
                evaluation.violated_constraint_ages,
                evaluation.diagnostics + (("DUPLICATE_TOP3",) if "DUPLICATE_TOP3" not in evaluation.diagnostics else ()),
            )
            for evaluation in evaluations
        )
    return evaluations


def _record(
    response: ModelResponse, evaluations: tuple[GuessEvaluation, ...], prompt: str,
    proposal_type: str, decision_round: int, state: GameState,
    feasible: tuple[str, ...],
) -> ProposalRecord:
    valid_legal = filter_candidates(state.legal_guesses, state.history)
    gains = tuple(
        information_gain(item.normalized, feasible) if item.valid else None for item in evaluations
    )
    return ProposalRecord(
        decision_round, proposal_type, response.raw_text, evaluations, response.protocol_error,
        hashlib.sha256(prompt.encode()).hexdigest(), len(feasible), gains,
        best_information_gain(valid_legal, feasible),
    )


async def run_game(adapter: ModelAdapter, condition: Condition, state: GameState) -> GameResult:
    proposals: list[ProposalRecord] = []
    initial_invalid = repairs = repair_successes = forfeits = 0

    for decision_round in range(1, 7):
        feasible_before = filter_candidates(state.initial_secrets, state.history)
        prompt = build_prompt(condition, state, decision_round)
        response = await adapter.predict(prompt)
        evaluations = _evaluate(response, state, condition, decision_round)
        top1 = evaluations[0] if evaluations else None
        proposals.append(_record(response, evaluations, prompt, "initial", decision_round,
                                 state, feasible_before))

        if top1 is None or not top1.valid:
            initial_invalid += 1
            repairs += 1
            rejected = top1.raw if top1 else "<unavailable>"
            error: GuessStatus | str = top1.status if top1 else "PROTOCOL_ERROR"
            prompt = build_prompt(condition, state, decision_round, rejected, error)
            response = await adapter.predict(prompt)
            evaluations = _evaluate(response, state, condition, decision_round)
            top1 = evaluations[0] if evaluations else None
            proposals.append(_record(response, evaluations, prompt, "repair", decision_round,
                                     state, feasible_before))
            if top1 is None or not top1.valid:
                forfeits += 1
                continue
            repair_successes += 1

        accepted = top1.normalized
        feedback = score(state.secret, accepted)
        state.accept(accepted, feedback, decision_round)
        feasible_after = filter_candidates(state.initial_secrets, state.history)
        proposals[-1] = replace(
            proposals[-1], accepted_guess=accepted,
            feedback=tuple(item.value for item in feedback), candidate_count_after=len(feasible_after),
        )
        if accepted == state.secret:
            break

    solved = state.solved
    solve_round = state.history[-1].decision_round if solved else None
    summary = GameSummary(solved, solve_round, solve_round or 7, len(state.history), initial_invalid,
                          repairs, repair_successes, forfeits)
    return GameResult(tuple(proposals), summary, state)
