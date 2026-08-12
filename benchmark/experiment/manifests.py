from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

from benchmark import BENCHMARK_VERSION


def stable_seed(master_seed: int, *labels: str) -> int:
    value = "\0".join((str(master_seed), *labels)).encode()
    return int.from_bytes(hashlib.sha256(value).digest()[:8], "big")


def load_words(path: Path) -> tuple[str, ...]:
    words = tuple(path.read_text().splitlines())
    if len(words) != len(set(words)) or any(
        len(word) != 5 or not word.isascii() or not word.isalpha() or not word.islower()
        for word in words
    ):
        raise ValueError(f"{path} must contain unique normalized five-letter words")
    return words


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _dynamic(words: tuple[str, ...], count: int, seed: int, split: str) -> list[dict]:
    records = []
    for index in range(count):
        game_id = f"dynamic_{split}_{index:04d}"
        pool_seed = stable_seed(seed, "pool", game_id)
        secret_seed = stable_seed(seed, "secret", game_id)
        pool = random.Random(pool_seed).sample(words, 256)
        records.append(
            {
                "benchmark_version": BENCHMARK_VERSION,
                "game_id": game_id,
                "pool_seed": pool_seed,
                "secret_seed": secret_seed,
                "pool": pool,
                "secret": random.Random(secret_seed).choice(pool),
            }
        )
    return records


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text("".join(json.dumps(record, separators=(",", ":")) + "\n" for record in records))


def generate_manifests(
    answers: tuple[str, ...], dynamic_words: tuple[str, ...], output: Path, master_seed: int,
    dev_count: int = 10, eval_count: int = 150,
) -> dict[str, str]:
    if len(answers) < dev_count + eval_count:
        raise ValueError("historical answer list is too small")
    if len(dynamic_words) < 256:
        raise ValueError("dynamic vocabulary must contain at least 256 words")
    output.mkdir(parents=True, exist_ok=True)
    historical_order = random.Random(stable_seed(master_seed, "historical", "all")).sample(
        answers, dev_count + eval_count
    )
    datasets = {
        "dev_historical": [
            {"benchmark_version": BENCHMARK_VERSION, "game_id": f"hist_dev_{i:04d}", "secret": word}
            for i, word in enumerate(historical_order[:dev_count])
        ],
        "eval_historical": [
            {"benchmark_version": BENCHMARK_VERSION, "game_id": f"hist_eval_{i:04d}", "secret": word}
            for i, word in enumerate(historical_order[dev_count:])
        ],
        "dev_dynamic": _dynamic(dynamic_words, dev_count, master_seed, "dev"),
        "eval_dynamic": _dynamic(dynamic_words, eval_count, master_seed, "eval"),
    }
    hashes = {}
    for name, records in datasets.items():
        path = output / f"{name}.jsonl"
        _write_jsonl(path, records)
        hashes[name] = file_sha256(path)
    return hashes
