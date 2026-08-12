from math import isclose, log2

from benchmark.engine.information import (
    FeedbackMatrix, best_information_gain, information_gain, write_feedback_matrix,
)


def test_hand_enumerable_information_gain() -> None:
    secrets = ("cigar", "rebut")
    assert isclose(information_gain("cigar", secrets), 1.0)
    assert 0 <= information_gain("cigar", secrets) <= log2(len(secrets))


def test_zero_information_and_oracle() -> None:
    secrets = ("cigar", "rebut")
    assert information_gain("xxxxx", secrets) == 0
    expected = max(information_gain(g, secrets) for g in ("cigar", "xxxxx"))
    assert best_information_gain(("cigar", "xxxxx"), secrets) == expected


def test_feedback_matrix_matches_direct_information_gain(tmp_path) -> None:
    guesses = ("cigar", "rebut", "sissy")
    secrets = ("cigar", "rebut")
    path = tmp_path / "feedback.bin"
    write_feedback_matrix(path, guesses, secrets)
    matrix = FeedbackMatrix(path, guesses, secrets)
    for guess in guesses:
        assert matrix.information_gain(guess, secrets) == information_gain(guess, secrets)
    assert matrix.best_information_gain(guesses, secrets) == best_information_gain(guesses, secrets)
