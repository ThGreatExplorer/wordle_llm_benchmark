from itertools import product
from pathlib import Path

import yaml

from benchmark.experiment.manifests import load_game_states, load_words
from benchmark.prompts import build_prompt
from benchmark.types import Condition, GameMode


def test_reasoning_suite_is_exact_frozen_matrix() -> None:
    suite = yaml.safe_load(Path("configs/reasoning_suite.yaml").read_text())
    assert suite == {
        "models_config": "configs/reasoning_models.yaml",
        "models": ["gpt5_medium", "gpt56_medium"],
        "conditions": ["hist_named", "hist_unnamed", "dynamic_256"],
        "modes": ["normal", "strict"],
        "split": "eval", "games_per_run": 150, "reasoning_effort": "medium",
        "request_timeout_seconds": 120, "max_output_tokens": 2048, "concurrency": 4,
    }
    runs = list(product(suite["models"], suite["conditions"], suite["modes"]))
    assert len(runs) == 12 and len(runs) * suite["games_per_run"] == 1800
    assert not {model for model, _, _ in runs} & {"gpt4o", "qwen3_8b", "qwen3_14b", "qwen3_32b"}


def test_medium_configs_preserve_baseline_model_and_freeze_treatment() -> None:
    suite = yaml.safe_load(Path("configs/reasoning_suite.yaml").read_text())
    models = yaml.safe_load(Path(suite["models_config"]).read_text())["models"]
    baselines = yaml.safe_load(Path("configs/models.yaml").read_text())["models"]
    for baseline, medium in (("gpt5", "gpt5_medium"), ("gpt56", "gpt56_medium")):
        assert models[medium]["model"] == baselines[baseline]["model"]
        assert models[medium]["provider"] == baselines[baseline]["provider"] == "openai"
        assert models[medium]["reasoning_effort"] == "medium"
        assert models[medium]["request_timeout_seconds"] == 120
        assert models[medium]["max_output_tokens"] == 2048
        assert baselines[baseline]["reasoning_effort"] != "medium"


def test_reasoning_pairs_use_identical_eval_instances_and_prompts() -> None:
    config = yaml.safe_load(Path("configs/benchmark.yaml").read_text())
    answers, extra = load_words(Path(config["answers"])), load_words(Path(config["extra_guesses"]))
    for condition in Condition:
        name = "dynamic" if condition is Condition.DYNAMIC_256 else "historical"
        games = load_game_states(
            Path(config["manifests"]) / f"eval_{name}.jsonl", condition, answers, extra,
            Path(config["historical_feedback_matrix"]),
        )
        assert len(games) == 150 and len({game_id for game_id, _ in games}) == 150
        _, state = games[0]
        baseline_prompt = build_prompt(condition, state, 1)
        medium_prompt = build_prompt(condition, state, 1)
        assert baseline_prompt == medium_prompt
        assert {mode.value for mode in GameMode} == {"normal", "strict"}
