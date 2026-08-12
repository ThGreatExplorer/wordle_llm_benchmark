import pytest

from benchmark.engine.feedback import score
from benchmark.prompts import build_prompt
from benchmark.prompts.builders import BANNED
from benchmark.types import Condition, GameState


def state(pool: tuple[str, ...] = ("crane", "slate", "trace")) -> GameState:
    result = GameState("slate", pool, pool)
    result.accept("crane", score("slate", "crane"), 1)
    return result


@pytest.mark.parametrize("condition", [Condition.HIST_UNNAMED, Condition.DYNAMIC_256])
def test_unnamed_prompts_are_clean_and_complete(condition: Condition) -> None:
    pool = tuple(f"a{n:04d}" for n in range(256)) if condition is Condition.DYNAMIC_256 else ("crane", "slate")
    prompt = build_prompt(condition, state(pool), 2)
    assert not any(term in prompt.lower() for term in BANNED)
    assert "crane:" in prompt and "Current decision round: 2" in prompt
    if condition is Condition.DYNAMIC_256:
        assert " ".join(pool) in prompt


def test_dynamic_prompt_rejects_wrong_pool_size() -> None:
    with pytest.raises(ValueError, match="256"):
        build_prompt(Condition.DYNAMIC_256, state(), 2)


def test_repair_only_reveals_rejected_guess_and_class() -> None:
    prompt = build_prompt(Condition.HIST_UNNAMED, state(), 2, "cigar", "CONSTRAINT_ERROR")
    assert '"cigar"' in prompt and "CONSTRAINT_ERROR" in prompt
    assert "violated" not in prompt.lower()


def test_banned_legal_guess_is_letter_spaced_in_unnamed_history() -> None:
    result = GameState("slate", ("slate",), ("grays", "slate"))
    result.accept("grays", score("slate", "grays"), 1)
    prompt = build_prompt(Condition.HIST_UNNAMED, result, 2)
    assert "g r a y s:" in prompt and "grays" not in prompt.lower()
