from collections import Counter
from collections.abc import Iterable, Sequence
from math import log2

from benchmark.engine.feedback import score


def information_gain(guess: str, feasible_secrets: Sequence[str]) -> float:
    if not feasible_secrets:
        raise ValueError("feasible secret set must not be empty")
    counts = Counter(score(secret, guess) for secret in feasible_secrets)
    total = len(feasible_secrets)
    return log2(total) - sum((count / total) * log2(count) for count in counts.values())


def best_information_gain(valid_guesses: Iterable[str], feasible_secrets: Sequence[str]) -> float:
    guesses = tuple(valid_guesses)
    if not guesses:
        raise ValueError("valid guess set must not be empty")
    return max(information_gain(guess, feasible_secrets) for guess in guesses)

