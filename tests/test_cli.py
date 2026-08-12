import pytest
import yaml
from pathlib import Path

from benchmark.cli import _freeze_metadata


def test_run_metadata_cannot_change_on_resume(tmp_path) -> None:
    path = tmp_path / "metadata.json"
    _freeze_metadata(path, {"run_id": "one"})
    _freeze_metadata(path, {"run_id": "one"})
    with pytest.raises(ValueError, match="differs"):
        _freeze_metadata(path, {"run_id": "two"})


def test_model_config_has_exact_frozen_tracks() -> None:
    models = yaml.safe_load(Path("configs/models.yaml").read_text())["models"]
    assert set(models) == {"gpt4o", "gpt5", "gpt56", "qwen3_4b", "qwen3_8b", "qwen3_14b", "qwen3_32b"}
