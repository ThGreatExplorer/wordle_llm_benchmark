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

from benchmark.experiment.manifests import generate_manifests, load_game_states, load_words
from benchmark import BENCHMARK_VERSION, PROMPT_VERSION
from benchmark.experiment.batch import run_batch
from benchmark.providers import MockAdapter, OpenAIResponsesAdapter, OpenRouterAdapter
from benchmark.types import Condition


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _freeze_metadata(path: Path, metadata: dict) -> None:
    serialized = json.dumps(metadata, indent=2, sort_keys=True) + "\n"
    if path.exists() and path.read_text() != serialized:
        raise ValueError(f"run metadata differs from existing {path}")
    path.write_text(serialized)


def _resume_metadata(path: Path, metadata: dict) -> None:
    if path.exists():
        metadata["started_at_utc"] = json.loads(path.read_text())["started_at_utc"]
    _freeze_metadata(path, metadata)


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"required environment variable {name} is not set")
    return value


def _metadata(
    run_id: str, config_path: Path, models_path: Path, config: dict,
    selected_model: dict, manifest: Path,
) -> dict:
    return {
        "run_id": run_id,
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
        ).stdout.strip() or None,
        "benchmark_version": BENCHMARK_VERSION,
        "prompt_version": PROMPT_VERSION,
        "manifest_hashes": {
            path.name: _hash(path) for path in sorted(Path(config["manifests"]).glob("*.jsonl"))
        },
        "word_list_hashes": {
            name: _hash(Path(config[name]))
            for name in ("answers", "extra_guesses", "dynamic_vocabulary")
        },
        "models_config_hash": _hash(models_path),
        "benchmark_config_hash": _hash(config_path),
        "lock_hash": _hash(Path("uv.lock")),
        "python": sys.version,
        "platform": platform.platform(),
        "selected_manifest": manifest.name,
        "selected_model_config": selected_model,
    }


def main() -> None:
    parser = argparse.ArgumentParser(prog="wordle-llm-benchmark")
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate = subparsers.add_parser("generate-manifests")
    generate.add_argument("--config", type=Path, default=Path("configs/benchmark.yaml"))
    generate.add_argument("--force", action="store_true")
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
    mock = subparsers.add_parser("run-mock")
    mock.add_argument("--config", type=Path, default=Path("configs/benchmark.yaml"))
    mock.add_argument("--condition", type=Condition, choices=list(Condition), default=Condition.DYNAMIC_256)
    mock.add_argument("--run-id", required=True)
    mock.add_argument("--results", type=Path, default=Path("results"))
    args = parser.parse_args()
    if args.command == "generate-manifests":
        config = yaml.safe_load(args.config.read_text())
        hashes = generate_manifests(
            load_words(Path(config["answers"])), load_words(Path(config["dynamic_vocabulary"])),
            Path(config["manifests"]), config["master_seed"], force=args.force,
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
        elif model_config["provider"] == "openrouter":
            api_key_env = model_config.get("api_key_env", "OPENROUTER_API_KEY")
            adapter = OpenRouterAdapter(
                model_config["model"],
                api_key=_required_env(api_key_env),
                upstream_provider=model_config["upstream_provider"],
                base_url=model_config["base_url"],
                temperature=model_config.get("temperature", 0),
                reasoning_effort=model_config["reasoning_effort"],
                allow_fallbacks=model_config["allow_fallbacks"],
                require_parameters=model_config["require_parameters"],
            )
        else:
            raise ValueError(f"unknown provider {model_config['provider']}")
        manifest_name = "dynamic" if args.condition is Condition.DYNAMIC_256 else "historical"
        manifest = Path(benchmark_config["manifests"]) / f"{args.split}_{manifest_name}.jsonl"
        games = load_game_states(
            manifest, args.condition, load_words(Path(benchmark_config["answers"])),
            load_words(Path(benchmark_config["extra_guesses"])),
        )
        output = args.results / args.run_id
        output.mkdir(parents=True, exist_ok=True)
        metadata = _metadata(args.run_id, args.config, args.models_config, benchmark_config,
                             model_config, manifest)
        metadata_path = output / "metadata.json"
        _resume_metadata(metadata_path, metadata)
        prices = (
            model_config.get("input_price_per_million", 0),
            model_config.get("output_price_per_million", 0),
            model_config.get("reasoning_price_per_million", 0),
        )
        results = asyncio.run(run_batch(
            adapter, args.condition, games, output / "proposals.jsonl", output / "summaries.jsonl",
            run_id=args.run_id, model_key=args.model, concurrency=args.concurrency,
            max_cost_usd=args.max_cost_usd, prices=prices,
            metadata={"benchmark_version": BENCHMARK_VERSION, "prompt_version": PROMPT_VERSION,
                      "manifest_hash": _hash(manifest), "model_config_hash": _hash(args.models_config),
                      "provider": model_config["provider"], "requested_model_id": model_config["model"]},
        ))
        print(f"completed {len(results)} games")
    elif args.command == "run-mock":
        config = yaml.safe_load(args.config.read_text())
        manifest_name = "dynamic" if args.condition is Condition.DYNAMIC_256 else "historical"
        manifest = Path(config["manifests"]) / f"dev_{manifest_name}.jsonl"
        game_id, state = load_game_states(
            manifest, args.condition, load_words(Path(config["answers"])),
            load_words(Path(config["extra_guesses"])),
        )[0]
        alternatives = [word for word in state.legal_guesses if word != state.secret][:2]
        adapter = MockAdapter([[state.secret, *alternatives]])
        output = args.results / args.run_id
        output.mkdir(parents=True, exist_ok=True)
        models_path = Path("configs/models.yaml")
        metadata = _metadata(args.run_id, args.config, models_path, config,
                             {"provider": "mock", "model": "deterministic-secret"}, manifest)
        _resume_metadata(output / "metadata.json", metadata)
        results = asyncio.run(run_batch(
            adapter, args.condition, [(game_id, state)], output / "proposals.jsonl",
            output / "summaries.jsonl", run_id=args.run_id, model_key="mock",
            metadata={"benchmark_version": BENCHMARK_VERSION, "prompt_version": PROMPT_VERSION,
                      "manifest_hash": _hash(manifest), "model_config_hash": _hash(models_path),
                      "provider": "mock", "requested_model_id": "deterministic-secret"},
        ))
        print(f"completed {len(results)} game")
