from pathlib import Path

import pytest

from scripts.run_suite import commands


def test_inference_suite_is_openai_only_full_matrix() -> None:
    runs = commands("inference-eval", results=Path("results"), concurrency=4)
    assert len(runs) == 18
    assert {run[run.index("--model") + 1] for run in runs} == {"gpt4o", "gpt5", "gpt56"}
    assert all("qwen" not in " ".join(run) for run in runs)
    assert all(run[run.index("--split") + 1] == "eval" and "--limit" not in run for run in runs)


def test_reasoning_suite_uses_only_medium_configs_and_dev_limit() -> None:
    runs = commands("reasoning-dev", results=Path("out"), concurrency=2, dev_limit=1)
    assert len(runs) == 12
    assert {run[run.index("--model") + 1] for run in runs} == {"gpt5_medium", "gpt56_medium"}
    assert all(run[run.index("--models-config") + 1] == "configs/reasoning_models.yaml" for run in runs)
    assert all(run[run.index("--limit") + 1] == "1" for run in runs)
    run_ids = {run[run.index("--run-id") + 1] for run in runs}
    assert all(run_id.startswith(("gpt5medium-", "gpt56medium-")) for run_id in run_ids)
    assert all("-medium-" not in run_id for run_id in run_ids)


def test_eval_rejects_dev_limit() -> None:
    with pytest.raises(ValueError, match="evaluation"):
        commands("reasoning-eval", results=Path("results"), concurrency=4, dev_limit=1)


def test_suite_passes_force_resume_to_every_run() -> None:
    runs = commands("inference-dev", results=Path("results"), concurrency=4, force_resume=True)
    assert all("--force-resume" in run for run in runs)
