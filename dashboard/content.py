from __future__ import annotations

from pathlib import Path

import yaml

CONTENT = Path(__file__).with_name("content")


def load_content(name: str) -> dict | list:
    if name not in {"metrics", "findings", "caveats"}:
        raise ValueError(f"unknown interpretation content: {name}")
    return yaml.safe_load((CONTENT / f"{name}.yaml").read_text())


def metric_help(metric: str) -> dict:
    metrics = load_content("metrics")
    if metric not in metrics:
        raise KeyError(f"No interpretation is defined for {metric}")
    return metrics[metric]
