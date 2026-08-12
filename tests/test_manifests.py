import json
from pathlib import Path

from benchmark.experiment.manifests import generate_manifests, stable_seed
from benchmark import BENCHMARK_VERSION


def test_manifest_generation_is_reproducible_and_disjoint(tmp_path: Path) -> None:
    answers = tuple(f"a{n:04d}" for n in range(170))
    dynamic = tuple(f"b{n:04d}" for n in range(300))
    first = tmp_path / "first"
    second = tmp_path / "second"
    assert generate_manifests(answers, dynamic, first, 42) == generate_manifests(answers, dynamic, second, 42)
    dev = [json.loads(line) for line in (first / "dev_historical.jsonl").read_text().splitlines()]
    evaluation = [json.loads(line) for line in (first / "eval_historical.jsonl").read_text().splitlines()]
    dynamic_eval = [json.loads(line) for line in (first / "eval_dynamic.jsonl").read_text().splitlines()]
    assert len(dev) == 10 and len(evaluation) == len(dynamic_eval) == 150
    assert {row["secret"] for row in dev}.isdisjoint(row["secret"] for row in evaluation)
    assert all(len(row["pool"]) == len(set(row["pool"])) == 256 and row["secret"] in row["pool"] for row in dynamic_eval)
    assert stable_seed(42, "pool", "x") != stable_seed(42, "secret", "x")


def test_frozen_manifest_shapes() -> None:
    root = Path("data/manifests")
    historical = [json.loads(line) for line in (root / "eval_historical.jsonl").read_text().splitlines()]
    dynamic = [json.loads(line) for line in (root / "eval_dynamic.jsonl").read_text().splitlines()]
    assert len(historical) == len(dynamic) == 150
    assert BENCHMARK_VERSION == "mvp-v2"
    assert all(row["benchmark_version"] == BENCHMARK_VERSION for row in historical + dynamic)
    assert len({row["secret"] for row in historical}) == 150
    assert all(len(row["pool"]) == len(set(row["pool"])) == 256 and row["secret"] in row["pool"] for row in dynamic)
