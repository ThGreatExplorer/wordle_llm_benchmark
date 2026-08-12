import pytest
import yaml
import json
import sys
from pathlib import Path

from benchmark.cli import _freeze_metadata, _positive_int, _required_env, main


def test_run_metadata_cannot_change_on_resume(tmp_path) -> None:
    path = tmp_path / "metadata.json"
    _freeze_metadata(path, {"run_id": "one"})
    _freeze_metadata(path, {"run_id": "one"})
    with pytest.raises(ValueError, match="differs"):
        _freeze_metadata(path, {"run_id": "two"})


def test_model_config_has_exact_frozen_tracks() -> None:
    models = yaml.safe_load(Path("configs/models.yaml").read_text())["models"]
    assert set(models) == {"gpt4o", "gpt5", "gpt56", "qwen3_8b", "qwen3_14b", "qwen3_32b"}
    expected = {
        "qwen3_8b": "Qwen/Qwen3-8B:nscale",
        "qwen3_14b": "Qwen/Qwen3-14B:nscale",
        "qwen3_32b": "Qwen/Qwen3-32B:nscale",
    }
    assert {key: models[key]["model"] for key in expected} == expected
    assert all(models[key]["base_url"] == "https://router.huggingface.co/v1" for key in expected)
    assert all(models[key]["api_key_env"] == "HF_TOKEN" for key in expected)
    assert all(models[key]["provider"] == "huggingface_nscale" for key in expected)
    assert all(models[key]["inference_provider"] == "nscale" for key in expected)
    assert all(models[key]["reasoning_effort"] == "none" for key in models if key.startswith("qwen"))
    assert all(models[key]["temperature"] == 0 for key in expected)
    assert all(models[key]["input_price_per_million"] is None for key in expected)


def test_required_provider_key_fails_before_a_request(monkeypatch) -> None:
    monkeypatch.delenv("HF_TOKEN", raising=False)
    with pytest.raises(ValueError, match="HF_TOKEN"):
        _required_env("HF_TOKEN")


def test_limit_must_be_positive() -> None:
    assert _positive_int("1") == 1
    with pytest.raises(Exception, match="positive"):
        _positive_int("0")


def test_cli_runs_one_mock_game_from_frozen_dev_manifest(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", [
        "benchmark", "run-mock", "--condition", "dynamic_256",
        "--run-id", "mock-real-data", "--results", str(tmp_path),
    ])
    main()
    output = tmp_path / "mock-real-data"
    summary = json.loads((output / "summaries.jsonl").read_text())
    proposal = json.loads((output / "proposals.jsonl").read_text())
    metadata = json.loads((output / "metadata.json").read_text())
    assert capsys.readouterr().out == "completed 1 game\n"
    assert summary["solved"] and summary["game_id"] == "dynamic_dev_0000"
    assert proposal["prompt_version"] == "prompt-v4"
    assert {
        "run_id", "started_at_utc", "git_commit", "benchmark_version", "prompt_version",
        "manifest_hashes", "word_list_hashes", "models_config_hash", "benchmark_config_hash",
        "lock_hash", "python", "platform", "selected_manifest", "selected_model_config",
    } <= metadata.keys()
