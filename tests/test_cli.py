import pytest
import yaml
import json
import sys
from pathlib import Path

from benchmark.cli import _freeze_metadata, _required_env, main


def test_run_metadata_cannot_change_on_resume(tmp_path) -> None:
    path = tmp_path / "metadata.json"
    _freeze_metadata(path, {"run_id": "one"})
    _freeze_metadata(path, {"run_id": "one"})
    with pytest.raises(ValueError, match="differs"):
        _freeze_metadata(path, {"run_id": "two"})


def test_model_config_has_exact_frozen_tracks() -> None:
    models = yaml.safe_load(Path("configs/models.yaml").read_text())["models"]
    assert set(models) == {"gpt4o", "gpt5", "gpt56", "qwen3_8b", "qwen3_14b", "qwen3_32b"}
    assert all(models[key]["base_url"] == "https://openrouter.ai/api/v1" for key in models if key.startswith("qwen"))
    assert all(models[key]["api_key_env"] == "OPENROUTER_API_KEY" for key in models if key.startswith("qwen"))
    assert {models[key]["upstream_provider"] for key in models if key.startswith("qwen")} == {"alibaba", "deepinfra"}
    assert all(models[key]["provider"] == "openrouter" for key in models if key.startswith("qwen"))
    assert all(models[key]["allow_fallbacks"] is False for key in models if key.startswith("qwen"))
    assert all(models[key]["require_parameters"] is True for key in models if key.startswith("qwen"))
    assert all(models[key]["reasoning_effort"] == "none" for key in models if key.startswith("qwen"))


def test_required_provider_key_fails_before_a_request(monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        _required_env("OPENROUTER_API_KEY")


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
    assert proposal["prompt_version"] == "prompt-v2"
    assert {
        "run_id", "started_at_utc", "git_commit", "benchmark_version", "prompt_version",
        "manifest_hashes", "word_list_hashes", "models_config_hash", "benchmark_config_hash",
        "lock_hash", "python", "platform", "selected_manifest", "selected_model_config",
    } <= metadata.keys()
