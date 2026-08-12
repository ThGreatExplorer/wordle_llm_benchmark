from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from benchmark.experiment.manifests import generate_manifests, load_words
from benchmark.experiment.batch import run_batch
from benchmark.providers import OpenAICompatibleAdapter, OpenAIResponsesAdapter
from benchmark.types import Condition, GameState


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _freeze_metadata(path: Path, metadata: dict) -> None:
    serialized = json.dumps(metadata, indent=2, sort_keys=True) + "\n"
    if path.exists() and path.read_text() != serialized:
        raise ValueError(f"run metadata differs from existing {path}")
    path.write_text(serialized)


def _states(manifest: Path, condition: Condition, answers: Path, extras: Path):
    records = [json.loads(line) for line in manifest.read_text().splitlines()]
    if condition is Condition.DYNAMIC_256:
        return [(row["game_id"], GameState(row["secret"], tuple(row["pool"]), tuple(row["pool"]))) for row in records]
    secrets = load_words(answers)
    legal = tuple(dict.fromkeys((*secrets, *load_words(extras))))
    return [(row["game_id"], GameState(row["secret"], secrets, legal)) for row in records]


def main() -> None:
    parser = argparse.ArgumentParser(prog="wordle-llm-benchmark")
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate = subparsers.add_parser("generate-manifests")
    generate.add_argument("--config", type=Path, default=Path("configs/benchmark.yaml"))
    run = subparsers.add_parser("run")
    run.add_argument("--config", type=Path, default=Path("configs/benchmark.yaml"))
    run.add_argument("--models-config", type=Path, default=Path("configs/models.yaml"))
    run.add_argument("--model", required=True)
    run.add_argument("--condition", type=Condition, choices=list(Condition), required=True)
    run.add_argument("--split", choices=("dev", "eval"), default="dev")
    run.add_argument("--run-id", required=True)
    run.add_argument("--results", type=Path, default=Path("results"))
    run.add_argument("--concurrency", type=int, default=1)
    run.add_argument("--max-cost-usd", type=float)
    args = parser.parse_args()
    if args.command == "generate-manifests":
        config = yaml.safe_load(args.config.read_text())
        hashes = generate_manifests(
            load_words(Path(config["answers"])), load_words(Path(config["dynamic_vocabulary"])),
            Path(config["manifests"]), config["master_seed"],
        )
        for name, digest in hashes.items():
            print(f"{name}: {digest}")
    elif args.command == "run":
        benchmark_config = yaml.safe_load(args.config.read_text())
        model_config = yaml.safe_load(args.models_config.read_text())["models"][args.model]
        if model_config["provider"] == "openai":
            adapter = OpenAIResponsesAdapter(
                model_config["model"], reasoning_effort=model_config.get("reasoning_effort"),
                temperature=model_config.get("temperature"),
            )
        else:
            adapter = OpenAICompatibleAdapter(
                model_config["model"], model_config["base_url"],
                api_key=os.environ.get(model_config.get("api_key_env", "QWEN_API_KEY"), "not-required"),
                temperature=model_config.get("temperature", 0),
                extra_body=model_config.get("extra_body"),
            )
        manifest_name = "dynamic" if args.condition is Condition.DYNAMIC_256 else "historical"
        manifest = Path(benchmark_config["manifests"]) / f"{args.split}_{manifest_name}.jsonl"
        games = _states(
            manifest, args.condition, Path(benchmark_config["answers"]),
            Path(benchmark_config["extra_guesses"]),
        )
        output = args.results / args.run_id
        output.mkdir(parents=True, exist_ok=True)
        metadata = {
            "run_id": args.run_id,
            "started_at_utc": datetime.now(timezone.utc).isoformat(),
            "git_commit": subprocess.run(
                ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
            ).stdout.strip() or None,
            "benchmark_version": "mvp-v1",
            "prompt_version": "prompt-v1",
            "manifest_hashes": {
                path.name: _hash(path)
                for path in sorted(Path(benchmark_config["manifests"]).glob("*.jsonl"))
            },
            "word_list_hashes": {
                "answers": _hash(Path(benchmark_config["answers"])),
                "extra_guesses": _hash(Path(benchmark_config["extra_guesses"])),
            },
            "models_config_hash": _hash(args.models_config),
            "benchmark_config_hash": _hash(args.config),
            "lock_hash": _hash(Path("uv.lock")),
            "python": sys.version,
            "platform": platform.platform(),
        }
        metadata_path = output / "metadata.json"
        if metadata_path.exists():
            metadata["started_at_utc"] = json.loads(metadata_path.read_text())["started_at_utc"]
        _freeze_metadata(metadata_path, metadata)
        prices = (
            model_config.get("input_price_per_million", 0),
            model_config.get("output_price_per_million", 0),
            model_config.get("reasoning_price_per_million", 0),
        )
        results = asyncio.run(run_batch(
            adapter, args.condition, games, output / "proposals.jsonl", output / "summaries.jsonl",
            run_id=args.run_id, model_key=args.model, concurrency=args.concurrency,
            max_cost_usd=args.max_cost_usd, prices=prices,
            metadata={"benchmark_version": "mvp-v1", "prompt_version": "prompt-v1",
                      "manifest_hash": _hash(manifest), "model_config_hash": _hash(args.models_config),
                      "provider": model_config["provider"], "requested_model_id": model_config["model"]},
        ))
        print(f"completed {len(results)} games")
