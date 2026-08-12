from collections import Counter
from functools import lru_cache

from benchmark.types import Feedback, FeedbackPattern


@lru_cache(maxsize=None)
def score(secret: str, guess: str) -> FeedbackPattern:
    """Return duplicate-aware feedback for two normalized five-letter words."""
    if len(secret) != 5 or len(guess) != 5:
        raise ValueError("secret and guess must each contain exactly five letters")

    result = [Feedback.ABSENT] * 5
    unmatched: Counter[str] = Counter()
    for index, (secret_letter, guess_letter) in enumerate(zip(secret, guess, strict=True)):
        if secret_letter == guess_letter:
            result[index] = Feedback.EXACT
        else:
            unmatched[secret_letter] += 1

    for index, guess_letter in enumerate(guess):
        if result[index] is Feedback.EXACT:
            continue
        if unmatched[guess_letter]:
            result[index] = Feedback.PRESENT
            unmatched[guess_letter] -= 1
    return tuple(result)  # type: ignore[return-value]

