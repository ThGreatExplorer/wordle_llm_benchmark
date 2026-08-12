from math import isclose, log2

from benchmark.engine.information import best_information_gain, information_gain


def test_hand_enumerable_information_gain() -> None:
    secrets = ("cigar", "rebut")
    assert isclose(information_gain("cigar", secrets), 1.0)
    assert 0 <= information_gain("cigar", secrets) <= log2(len(secrets))


def test_zero_information_and_oracle() -> None:
    secrets = ("cigar", "rebut")
    assert information_gain("xxxxx", secrets) == 0
    expected = max(information_gain(g, secrets) for g in ("cigar", "xxxxx"))
    assert best_information_gain(("cigar", "xxxxx"), secrets) == expected
