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
from benchmark.analysis import analyze_results
from benchmark import BENCHMARK_VERSION, PROMPT_VERSION
from benchmark.experiment.batch import run_batch
from benchmark.providers import HuggingFaceNscaleAdapter, MockAdapter, OpenAIResponsesAdapter
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


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def _metadata(
    run_id: str, config_path: Path, models_path: Path, config: dict,
    selected_model: dict, manifest: Path,
) -> dict:
    metadata = {
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
    if selected_model.get("provider") == "huggingface_nscale":
        metadata |= {
            "gateway": "huggingface_inference_providers",
            "inference_provider": selected_model["inference_provider"],
            "requested_model_id": selected_model["model"],
            "base_url": selected_model["base_url"],
            "reasoning_effort": selected_model["reasoning_effort"],
            "temperature": selected_model["temperature"],
            "structured_output_enabled": True,
            "max_retries": 5,
        }
    return metadata


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
    run.add_argument("--limit", type=_positive_int)
    mock = subparsers.add_parser("run-mock")
    mock.add_argument("--config", type=Path, default=Path("configs/benchmark.yaml"))
    mock.add_argument("--condition", type=Condition, choices=list(Condition), default=Condition.DYNAMIC_256)
    mock.add_argument("--run-id", required=True)
    mock.add_argument("--results", type=Path, default=Path("results"))
    analyze = subparsers.add_parser("analyze")
    analyze.add_argument("--results", type=Path, required=True)
    analyze.add_argument("--output", type=Path)
    analyze.add_argument("--bootstrap-resamples", type=_positive_int, default=10_000)
    analyze.add_argument("--seed", type=int, default=0)
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
        elif model_config["provider"] == "huggingface_nscale":
            api_key_env = model_config.get("api_key_env", "HF_TOKEN")
            adapter = HuggingFaceNscaleAdapter(
                model_config["model"],
                api_key=_required_env(api_key_env),
                base_url=model_config["base_url"],
                temperature=model_config.get("temperature", 0),
                reasoning_effort=model_config["reasoning_effort"],
            )
        else:
            raise ValueError(f"unknown provider {model_config['provider']}")
        manifest_name = "dynamic" if args.condition is Condition.DYNAMIC_256 else "historical"
        manifest = Path(benchmark_config["manifests"]) / f"{args.split}_{manifest_name}.jsonl"
        games = load_game_states(
            manifest, args.condition, load_words(Path(benchmark_config["answers"])),
            load_words(Path(benchmark_config["extra_guesses"])),
        )
        if args.limit is not None:
            games = games[:args.limit]
        output = args.results / args.run_id
        output.mkdir(parents=True, exist_ok=True)
        metadata = _metadata(args.run_id, args.config, args.models_config, benchmark_config,
                             model_config, manifest)
        metadata["game_limit"] = args.limit
        metadata_path = output / "metadata.json"
        _resume_metadata(metadata_path, metadata)
        prices = (
            model_config.get("input_price_per_million"),
            model_config.get("output_price_per_million"),
            model_config.get("reasoning_price_per_million", 0),
        )
        proposal_metadata = {
            "benchmark_version": BENCHMARK_VERSION, "prompt_version": PROMPT_VERSION,
            "manifest_hash": _hash(manifest), "model_config_hash": _hash(args.models_config),
            "provider": model_config["provider"], "requested_model_id": model_config["model"],
            "reasoning_effort": model_config.get("reasoning_effort"),
            "temperature": model_config.get("temperature"), "structured_output_enabled": True,
        }
        if model_config["provider"] == "huggingface_nscale":
            proposal_metadata |= {
                "gateway": "huggingface_inference_providers",
                "inference_provider": model_config["inference_provider"],
                "base_url": model_config["base_url"], "max_retries": 5,
            }
        results = asyncio.run(run_batch(
            adapter, args.condition, games, output / "proposals.jsonl", output / "summaries.jsonl",
            run_id=args.run_id, model_key=args.model, concurrency=args.concurrency,
            max_cost_usd=args.max_cost_usd, prices=prices,
            metadata=proposal_metadata,
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
    elif args.command == "analyze":
        output = args.output or args.results / "analysis"
        analyze_results(args.results, output, resamples=args.bootstrap_resamples, seed=args.seed)
        print(f"analysis written to {output}")
