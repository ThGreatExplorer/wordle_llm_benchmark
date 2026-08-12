import json
import re
from pathlib import Path

import pytest

from benchmark.experiment.manifests import file_sha256, generate_manifests, load_words, stable_seed
from benchmark import BENCHMARK_VERSION
from scripts.build_dynamic_dictionary import build, write_dictionary


def test_manifest_generation_is_reproducible_and_disjoint(tmp_path: Path) -> None:
    answers = tuple(f"a{n:04d}" for n in range(170))
    dynamic = tuple(f"b{n:04d}" for n in range(300))
    first = tmp_path / "first"
    second = tmp_path / "second"
    assert generate_manifests(answers, dynamic, first, 42) == generate_manifests(answers, dynamic, second, 42)
    with pytest.raises(FileExistsError):
        generate_manifests(answers, dynamic, first, 42)
    assert generate_manifests(answers, dynamic, first, 42, force=True) == generate_manifests(
        answers, dynamic, second, 42, force=True
    )
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


def test_frozen_dictionary_manifest_hashes_and_provenance(tmp_path: Path) -> None:
    data = Path("data")
    frozen = data / "frozen"
    manifests = data / "manifests"
    readme = (data / "README.md").read_text()
    documented = dict(re.findall(r"- `([^`]+)`: `([0-9a-f]{64})`", readme))
    artifacts = [
        frozen / "wordle_answers_2022.txt", frozen / "wordle_extra_guesses_2022.txt",
        frozen / "dynamic_master_5letter.txt", data / "raw/scowl_60_american.txt.gz",
        *sorted(manifests.glob("*.jsonl")),
    ]
    assert all(documented[path.name] == file_sha256(path) for path in artifacts)
    assert all(label in readme for label in ("Historical Wordle provenance", "SCOWL provenance", "wordfreq provenance"))

    master = load_words(frozen / "dynamic_master_5letter.txt")
    assert master == build(data / "raw/scowl_60_american.txt.gz", frozen / "wordle_answers_2022.txt")
    destination = tmp_path / "words.txt"
    write_dictionary(destination, ("abcde",))
    with pytest.raises(FileExistsError):
        write_dictionary(destination, ("fghij",))
    write_dictionary(destination, ("fghij",), force=True)
    assert destination.read_text() == "fghij\n"

    dev_dynamic = [json.loads(line) for line in (manifests / "dev_dynamic.jsonl").read_text().splitlines()]
    eval_dynamic = [json.loads(line) for line in (manifests / "eval_dynamic.jsonl").read_text().splitlines()]
    assert {row["pool_seed"] for row in dev_dynamic}.isdisjoint(row["pool_seed"] for row in eval_dynamic)
    assert {row["secret_seed"] for row in dev_dynamic}.isdisjoint(row["secret_seed"] for row in eval_dynamic)
    assert all(word in set(master) for row in dev_dynamic + eval_dynamic for word in row["pool"])
