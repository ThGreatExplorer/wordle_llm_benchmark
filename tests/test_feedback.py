import pytest

from benchmark.engine.feedback import score
from benchmark.types import Feedback as F


@pytest.mark.parametrize(
    ("secret", "guess", "expected"),
    [
        ("crane", "crane", (F.EXACT,) * 5),
        ("crane", "build", (F.ABSENT,) * 5),
        ("crane", "cater", (F.EXACT, F.PRESENT, F.ABSENT, F.PRESENT, F.PRESENT)),
        ("cigar", "array", (F.ABSENT, F.PRESENT, F.ABSENT, F.EXACT, F.ABSENT)),
        ("allee", "eagle", (F.PRESENT, F.PRESENT, F.ABSENT, F.PRESENT, F.EXACT)),
        ("sassy", "assay", (F.PRESENT, F.PRESENT, F.EXACT, F.ABSENT, F.EXACT)),
        ("belle", "eerie", (F.ABSENT, F.EXACT, F.ABSENT, F.ABSENT, F.EXACT)),
    ],
)
def test_score(secret: str, guess: str, expected: tuple[F, ...]) -> None:
    assert score(secret, guess) == expected


def test_score_rejects_wrong_length() -> None:
    with pytest.raises(ValueError):
        score("four", "words")
