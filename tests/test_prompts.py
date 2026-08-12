import pytest

from benchmark import PROMPT_VERSION
from benchmark.engine.feedback import score
from benchmark.prompts import build_prompt
from benchmark.prompts.builders import BANNED, instructional_prose
from benchmark.types import Condition, GameState


def state(pool: tuple[str, ...] = ("crane", "slate", "trace")) -> GameState:
    result = GameState("slate", pool, pool)
    result.accept("crane", score("slate", "crane"), 1)
    return result


def test_prompt_version_is_v4() -> None:
    assert PROMPT_VERSION == "prompt-v4"


@pytest.mark.parametrize("condition", [Condition.HIST_UNNAMED, Condition.DYNAMIC_256])
def test_unnamed_prompts_are_clean_and_complete(condition: Condition) -> None:
    pool = tuple(f"a{n:04d}" for n in range(256)) if condition is Condition.DYNAMIC_256 else ("crane", "slate")
    prompt = build_prompt(condition, state(pool), 2)
    assert not any(term in instructional_prose(condition).lower() for term in BANNED)
    assert "Row 1\nGuess: crane\nFeedback:" in prompt
    assert "Current decision round: 2 of 6" in prompt
    if condition is Condition.DYNAMIC_256:
        assert " ".join(pool) in prompt


def test_named_and_unnamed_have_equivalent_strict_semantics() -> None:
    named = instructional_prose(Condition.HIST_NAMED)
    unnamed = instructional_prose(Condition.HIST_UNNAMED)
    assert "Wordle" in named and not any(term in unnamed.lower() for term in BANNED)
    for phrase in (
        "Assign all EXACT matches first",
        "temporarily treat that proposed word as if it were the secret",
        "Re-evaluate each previous accepted guess",
        "must exactly match the five recorded feedback labels",
        "check every previous accepted row",
        "Only your first-ranked guess will actually be played",
        "second and third guesses",
        "silently verify each of your three proposed guesses",
        "Guess: ABCDE",
        "Feedback: EXACT ABSENT PRESENT ABSENT ABSENT",
        "Never propose an already accepted guess again unless its recorded feedback was EXACT EXACT EXACT EXACT EXACT",
    ):
        assert phrase in named and phrase in unnamed


def test_symbolic_consistency_example_is_identical_across_conditions() -> None:
    prompts = [instructional_prose(condition) for condition in Condition]
    example = """CONSISTENCY EXAMPLE

Suppose a previous accepted row is:

Guess: ABCDE
Feedback: EXACT ABSENT PRESENT ABSENT ABSENT

Then any later valid proposal must:
- have A in position 1;
- not contain B, D, or E;
- contain C somewhere other than position 3;
- also satisfy every other previous feedback row.

A proposal that violates even one of these requirements is invalid.

The letter strings in this example illustrate consistency logic only and are not legal guesses for the game."""
    assert all(prompt.count(example) == 1 for prompt in prompts)


def test_dynamic_prompt_rejects_wrong_pool_size() -> None:
    with pytest.raises(ValueError, match="256"):
        build_prompt(Condition.DYNAMIC_256, state(), 2)


def test_constraint_repair_explains_error_without_identifying_row() -> None:
    prompt = build_prompt(Condition.HIST_UNNAMED, state(), 2, "cigar", "CONSTRAINT_ERROR")
    assert '"cigar"' in prompt and "CONSTRAINT_ERROR" in prompt
    assert "would not reproduce its recorded five feedback labels exactly" in prompt
    assert "The specific violated row is not provided." in prompt


def test_dynamic_lexicon_repair_explains_candidate_restriction() -> None:
    pool = tuple(f"a{n:04d}" for n in range(256))
    prompt = build_prompt(Condition.DYNAMIC_256, state(pool), 2, "other", "LEXICON_ERROR")
    assert '"other"' in prompt and "was not one of the 256 candidate words" in prompt


def test_protocol_repair_has_no_fake_rejected_guess() -> None:
    prompt = build_prompt(Condition.HIST_NAMED, state(), 2, None, "PROTOCOL_ERROR")
    assert "Your previous response was rejected with PROTOCOL_ERROR" in prompt
    assert "<unavailable>" not in prompt and "previous first-ranked proposal" not in prompt


def test_lexical_payload_is_preserved_verbatim() -> None:
    result = GameState("slate", ("slate",), ("grays", "slate"))
    result.accept("grays", score("slate", "grays"), 1)
    prompt = build_prompt(Condition.HIST_UNNAMED, result, 2)
    assert "Guess: grays" in prompt


def test_dynamic_pool_is_complete_legal_set_in_fixed_verbatim_order() -> None:
    pool = tuple(f"x{n:04d}" for n in range(256))
    prompt = build_prompt(Condition.DYNAMIC_256, state(pool), 2)
    assert "These 256 words are also the complete legal guess set" in prompt
    assert " ".join(pool) in prompt
    assert all(prompt.count(word) == 1 for word in pool)


def test_empty_history_is_explicit() -> None:
    prompt = build_prompt(
        Condition.HIST_NAMED,
        GameState("slate", ("slate",), ("slate",)),
        1,
    )
    assert "Accepted feedback history:\n\n(none)" in prompt
    assert "Current decision round: 1 of 6" in prompt


def test_output_contract_has_no_lexical_examples() -> None:
    prose = instructional_prose(Condition.HIST_UNNAMED)
    assert '"guesses"' in prose
    assert not any(word in prose for word in ("crane", "slate", "trace"))
