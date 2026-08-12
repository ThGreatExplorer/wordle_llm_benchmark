import pytest
import yaml
from pathlib import Path

from benchmark.cli import _freeze_metadata, _required_env


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
    assert all(models[key]["extra_body"] == {
        "reasoning": {"effort": "none"}, "provider": {"require_parameters": True}
    } for key in models if key.startswith("qwen"))


def test_required_provider_key_fails_before_a_request(monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        _required_env("OPENROUTER_API_KEY")
