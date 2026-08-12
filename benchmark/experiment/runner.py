from __future__ import annotations

import json
import hashlib
from collections import Counter
from datetime import datetime, timezone
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
    input_tokens: int | None
    output_tokens: int | None
    reasoning_tokens: int | None
    latency_ms: float
    estimated_cost_usd: float | None
    provider_request_id: str | None
    returned_model_id: str | None
    returned_provider: str | None
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
    protocol_error_count: int
    format_error_count: int
    lexicon_error_count: int
    constraint_error_count: int
    input_tokens_total: int
    output_tokens_total: int
    reasoning_tokens_total: int
    estimated_cost_usd_total: float
    latency_ms_total: float


@dataclass(frozen=True)
class GameResult:
    proposals: tuple[ProposalRecord, ...]
    summary: GameSummary
    state: GameState


def append_result(
    proposal_path: Path, summary_path: Path, result: GameResult, metadata: dict[str, str]
) -> None:
    timestamp = datetime.now(timezone.utc).isoformat()
    with proposal_path.open("a") as proposals:
        for proposal in result.proposals:
            proposals.write(json.dumps(metadata | {"timestamp_utc": timestamp} | asdict(proposal), separators=(",", ":")) + "\n")
    with summary_path.open("a") as summaries:
        summaries.write(json.dumps(metadata | {"timestamp_utc": timestamp} | asdict(result.summary), separators=(",", ":")) + "\n")


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
    feasible: tuple[str, ...], input_price: float, output_price: float, reasoning_price: float,
) -> ProposalRecord:
    valid_legal = filter_candidates(state.legal_guesses, state.history)
    gains = tuple(
        information_gain(item.normalized, feasible) if item.valid else None for item in evaluations
    )
    cost = None
    if response.input_tokens is not None or response.output_tokens is not None or response.reasoning_tokens is not None:
        cost = (
            (response.input_tokens or 0) * input_price
            + (response.output_tokens or 0) * output_price
            + (response.reasoning_tokens or 0) * reasoning_price
        ) / 1_000_000
    return ProposalRecord(
        decision_round, proposal_type, response.raw_text, evaluations, response.protocol_error,
        hashlib.sha256(prompt.encode()).hexdigest(), len(feasible), gains,
        best_information_gain(valid_legal, feasible),
        response.input_tokens, response.output_tokens, response.reasoning_tokens,
        response.latency_ms, cost, response.provider_request_id, response.model_returned,
        response.provider_returned,
    )


async def run_game(
    adapter: ModelAdapter, condition: Condition, state: GameState, *,
    input_price_per_million: float = 0, output_price_per_million: float = 0,
    reasoning_price_per_million: float = 0,
) -> GameResult:
    proposals: list[ProposalRecord] = []
    initial_invalid = repairs = repair_successes = forfeits = 0

    for decision_round in range(1, 7):
        feasible_before = filter_candidates(state.initial_secrets, state.history)
        prompt = build_prompt(condition, state, decision_round)
        response = await adapter.predict(prompt)
        evaluations = _evaluate(response, state, condition, decision_round)
        top1 = evaluations[0] if evaluations else None
        proposals.append(_record(response, evaluations, prompt, "initial", decision_round,
                                 state, feasible_before, input_price_per_million,
                                 output_price_per_million, reasoning_price_per_million))

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
                                     state, feasible_before, input_price_per_million,
                                     output_price_per_million, reasoning_price_per_million))
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
    errors = Counter(
        evaluation.status
        for proposal in proposals
        for evaluation in proposal.evaluations
        if not evaluation.valid
    )
    summary = GameSummary(
        solved, solve_round, solve_round or 7, len(state.history), initial_invalid,
        repairs, repair_successes, forfeits,
        sum(proposal.protocol_error is not None for proposal in proposals),
        errors[GuessStatus.FORMAT_ERROR], errors[GuessStatus.LEXICON_ERROR],
        errors[GuessStatus.CONSTRAINT_ERROR],
        sum(item.input_tokens or 0 for item in proposals),
        sum(item.output_tokens or 0 for item in proposals),
        sum(item.reasoning_tokens or 0 for item in proposals),
        sum(item.estimated_cost_usd or 0 for item in proposals),
        sum(item.latency_ms for item in proposals),
    )
    return GameResult(tuple(proposals), summary, state)
