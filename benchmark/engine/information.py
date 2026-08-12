from collections import Counter
from collections.abc import Iterable, Sequence
import hashlib
from math import log2
import mmap
from pathlib import Path
import struct

from benchmark.engine.feedback import score
from benchmark.types import Feedback

MAGIC = b"WLBIG1\0\0"
HEADER = struct.Struct(">8sII32s32s")


def _words_hash(words: Sequence[str]) -> bytes:
    return hashlib.sha256(("\n".join(words) + "\n").encode()).digest()


def feedback_code(pattern: Sequence[Feedback]) -> int:
    values = {Feedback.ABSENT: 0, Feedback.PRESENT: 1, Feedback.EXACT: 2}
    code = 0
    for item in pattern:
        code = code * 3 + values[item]
    return code


class FeedbackMatrix:
    """Memory-mapped historical guess-by-answer feedback codes."""

    def __init__(self, path: Path, guesses: Sequence[str], secrets: Sequence[str]) -> None:
        self._file = path.open("rb")
        self._data = mmap.mmap(self._file.fileno(), 0, access=mmap.ACCESS_READ)
        magic, guess_count, secret_count, guess_hash, secret_hash = HEADER.unpack_from(self._data)
        if (magic, guess_count, secret_count, guess_hash, secret_hash) != (
            MAGIC, len(guesses), len(secrets), _words_hash(guesses), _words_hash(secrets)
        ) or len(self._data) != HEADER.size + len(guesses) * len(secrets):
            raise ValueError(f"{path} does not match the frozen historical vocabularies")
        self.guesses = tuple(guesses)
        self.secrets = tuple(secrets)
        self._guess_index = {word: index for index, word in enumerate(guesses)}
        self._secret_index = {word: index for index, word in enumerate(secrets)}

    def information_gain(self, guess: str, feasible_secrets: Sequence[str]) -> float:
        if not feasible_secrets:
            raise ValueError("feasible secret set must not be empty")
        row = HEADER.size + self._guess_index[guess] * len(self.secrets)
        counts = [0] * 243
        for secret in feasible_secrets:
            counts[self._data[row + self._secret_index[secret]]] += 1
        total = len(feasible_secrets)
        return log2(total) - sum((count / total) * log2(count) for count in counts if count)

    def best_information_gain(
        self, guesses: Iterable[str], feasible_secrets: Sequence[str]
    ) -> float:
        guesses = tuple(guesses)
        if not guesses:
            raise ValueError("valid guess set must not be empty")
        return max(self.information_gain(guess, feasible_secrets) for guess in guesses)


def write_feedback_matrix(path: Path, guesses: Sequence[str], secrets: Sequence[str]) -> None:
    if path.exists():
        raise FileExistsError(path)
    with path.open("wb") as handle:
        handle.write(HEADER.pack(MAGIC, len(guesses), len(secrets), _words_hash(guesses), _words_hash(secrets)))
        for guess in guesses:
            handle.write(bytes(feedback_code(score(secret, guess)) for secret in secrets))
            score.cache_clear()


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
