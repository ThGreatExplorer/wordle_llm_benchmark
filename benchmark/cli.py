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
from benchmark.experiment.batch import (
    clean_partial_proposals, completed_rows, partial_proposals, result_key, run_batch,
)
from benchmark.providers import HuggingFaceNscaleAdapter, MockAdapter, OpenAIResponsesAdapter
from benchmark.types import Condition, GameMode


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
    model_key: str, selected_model: dict, manifest: Path, condition: Condition,
    game_mode: GameMode, split: str, selected_game_ids: list[str], concurrency: int,
) -> dict:
    metadata = {
        "run_id": run_id,
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
        ).stdout.strip() or None,
        "benchmark_version": BENCHMARK_VERSION,
        "prompt_version": PROMPT_VERSION,
        "model_key": model_key,
        "condition": condition.value,
        "game_mode": game_mode.value,
        "split": split,
        "requested_games": len(selected_game_ids),
        "concurrency": concurrency,
        "selected_game_ids_hash": hashlib.sha256("\n".join(selected_game_ids).encode()).hexdigest(),
        "manifest_hashes": {
            path.name: _hash(path) for path in sorted(Path(config["manifests"]).glob("*.jsonl"))
        },
        "word_list_hashes": {
            name: _hash(Path(config[name]))
            for name in ("answers", "extra_guesses", "dynamic_vocabulary", "historical_feedback_matrix")
        },
        "models_config_hash": _hash(models_path),
        "benchmark_config_hash": _hash(config_path),
        "lock_hash": _hash(Path("uv.lock")),
        "python": sys.version,
        "platform": platform.platform(),
        "selected_manifest": manifest.name,
        "selected_manifest_hash": _hash(manifest),
        "selected_model_config": selected_model,
        "provider": selected_model["provider"],
        "requested_model_id": selected_model["model"],
        "reasoning_effort": selected_model.get("reasoning_effort"),
        "temperature": selected_model.get("temperature"),
        "request_timeout_seconds": selected_model.get("request_timeout_seconds"),
        "max_output_tokens": selected_model.get("max_output_tokens"),
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


def _run_rows(output: Path, metadata: dict) -> list[dict]:
    prefix = (
        metadata["run_id"], metadata["model_key"], metadata["condition"], metadata["game_mode"],
    )
    return [row for row in completed_rows(output / "summaries.jsonl") if result_key(row)[:4] == prefix]


def _print_status(output: Path, metadata: dict, *, startup: bool = False, concurrency: int | None = None) -> list[dict]:
    rows = _run_rows(output, metadata)
    requested, completed = metadata["requested_games"], len(rows)
    cost = sum(row.get("estimated_cost_usd_total") or 0 for row in rows)
    print(f"Run: {metadata['run_id']}")
    print(f"Model: {metadata['model_key']}")
    print(f"Condition: {metadata['condition']}")
    print(f"Mode: {metadata['game_mode']}")
    print(f"Reasoning effort: {metadata['selected_model_config'].get('reasoning_effort') or 'none'}")
    print(f"Split/manifest: {metadata['split']} / {metadata['selected_manifest']}")
    if startup:
        print(f"Requested games: {requested}\nCompleted: {completed}\nPending: {requested - completed}")
        if concurrency is not None:
            print(f"Concurrency: {concurrency}")
        print(f"Recorded completed-game cost: ${cost:.4f}")
        print("Resuming existing run." if completed else "Starting new run.")
    else:
        print(f"Benchmark version: {metadata['benchmark_version']}\nPrompt version: {metadata['prompt_version']}")
        print(f"\nRequested: {requested}\nCompleted: {completed}\nPending: {requested - completed}")
        print(f"Progress: {100 * completed / requested if requested else 100:.1f}%")
        print(f"\nSolved: {sum(bool(row.get('solved')) for row in rows)}")
        print(f"Unsolved: {sum(not row.get('solved') for row in rows)}")
        print(f"\nRecorded cost: ${cost:.4f}")
        print(f"Input tokens: {sum(row.get('input_tokens_total') or 0 for row in rows)}")
        print(f"Output tokens: {sum(row.get('output_tokens_total') or 0 for row in rows)}")
        print(f"Reasoning tokens: {sum(row.get('reasoning_tokens_total') or 0 for row in rows)}")
        _, orphan_keys = partial_proposals(output / "proposals.jsonl", output / "summaries.jsonl")
        orphan_rows = sum(
            result_key(row) in orphan_keys
            for row in (partial_proposals(output / "proposals.jsonl", output / "summaries.jsonl")[0])
        )
        if orphan_keys:
            print(f"\nIncomplete prior attempts: {len(orphan_keys)} games\nOrphan proposal rows: {orphan_rows}")
    return rows


def _print_completion(output: Path, metadata: dict) -> None:
    rows = _run_rows(output, metadata)
    total, solved = len(rows), sum(bool(row["solved"]) for row in rows)
    cost = sum(row.get("estimated_cost_usd_total") or 0 for row in rows)
    print("Run complete.")
    print(f"\nCompleted: {total}/{metadata['requested_games']}")
    print(f"Solve@6: {solved}/{total} ({100 * solved / total:.1f}%)")
    print(f"Mean score: {sum(row['round_score'] for row in rows) / total:.2f}")
    print(f"Total recorded cost: ${cost:.2f}")
    print(f"Input tokens: {sum(row.get('input_tokens_total') or 0 for row in rows)}")
    print(f"Output tokens: {sum(row.get('output_tokens_total') or 0 for row in rows)}")
    print(f"Reasoning tokens: {sum(row.get('reasoning_tokens_total') or 0 for row in rows)}")
    print(f"Results: {output}/")


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
    run.add_argument("--mode", type=GameMode, choices=list(GameMode), required=True)
    run.add_argument("--split", choices=("dev", "eval"), default="dev")
    run.add_argument("--run-id", required=True)
    run.add_argument("--results", type=Path, default=Path("results"))
    run.add_argument("--concurrency", type=int, default=1)
    run.add_argument("--max-cost-usd", type=float)
    run.add_argument("--limit", type=_positive_int)
    mock = subparsers.add_parser("run-mock")
    mock.add_argument("--config", type=Path, default=Path("configs/benchmark.yaml"))
    mock.add_argument("--condition", type=Condition, choices=list(Condition), default=Condition.DYNAMIC_256)
    mock.add_argument("--mode", type=GameMode, choices=list(GameMode), default=GameMode.NORMAL)
    mock.add_argument("--run-id", required=True)
    mock.add_argument("--results", type=Path, default=Path("results"))
    analyze = subparsers.add_parser("analyze")
    analyze.add_argument("--results", type=Path, required=True)
    analyze.add_argument("--output", type=Path)
    analyze.add_argument("--bootstrap-resamples", type=_positive_int, default=10_000)
    analyze.add_argument("--seed", type=int, default=0)
    status = subparsers.add_parser("status")
    status.add_argument("--results", type=Path, required=True)
    clean = subparsers.add_parser("clean-partials")
    clean.add_argument("--results", type=Path, required=True)
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
        manifest_name = "dynamic" if args.condition is Condition.DYNAMIC_256 else "historical"
        manifest = Path(benchmark_config["manifests"]) / f"{args.split}_{manifest_name}.jsonl"
        games = load_game_states(
            manifest, args.condition, load_words(Path(benchmark_config["answers"])),
            load_words(Path(benchmark_config["extra_guesses"])),
            Path(benchmark_config["historical_feedback_matrix"]),
        )
        if args.limit is not None:
            games = games[:args.limit]
        output = args.results / args.run_id
        output.mkdir(parents=True, exist_ok=True)
        metadata = _metadata(args.run_id, args.config, args.models_config, benchmark_config,
                             args.model, model_config, manifest, args.condition, args.mode,
                             args.split, [game_id for game_id, _ in games], args.concurrency)
        metadata["game_limit"] = args.limit
        metadata_path = output / "metadata.json"
        _resume_metadata(metadata_path, metadata)
        removed, incomplete = clean_partial_proposals(
            output / "proposals.jsonl", output / "summaries.jsonl"
        )
        if removed:
            print(f"Resume cleanup: removed {removed} proposal rows from {incomplete} incomplete prior attempt{'s' if incomplete != 1 else ''}.")
        rows = _print_status(output, metadata, startup=True, concurrency=args.concurrency)
        if len(rows) == len(games):
            print(f"Run already complete: {len(rows)}/{len(games)} games.\nNo provider calls required.")
            return
        if model_config["provider"] == "openai":
            adapter = OpenAIResponsesAdapter(
                model_config["model"], reasoning_effort=model_config.get("reasoning_effort"),
                temperature=model_config.get("temperature"),
                request_timeout_seconds=model_config.get("request_timeout_seconds"),
                max_output_tokens=model_config.get("max_output_tokens"),
            )
        elif model_config["provider"] == "huggingface_nscale":
            api_key_env = model_config.get("api_key_env", "HF_TOKEN")
            adapter = HuggingFaceNscaleAdapter(
                model_config["model"], api_key=_required_env(api_key_env),
                base_url=model_config["base_url"], temperature=model_config.get("temperature", 0),
                reasoning_effort=model_config["reasoning_effort"],
            )
        else:
            raise ValueError(f"unknown provider {model_config['provider']}")
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
            "request_timeout_seconds": model_config.get("request_timeout_seconds"),
            "max_output_tokens": model_config.get("max_output_tokens"),
        }
        if model_config["provider"] == "huggingface_nscale":
            proposal_metadata |= {
                "gateway": "huggingface_inference_providers",
                "inference_provider": model_config["inference_provider"],
                "base_url": model_config["base_url"], "max_retries": 5,
            }
        try:
            asyncio.run(run_batch(
                adapter, args.condition, games, output / "proposals.jsonl", output / "summaries.jsonl",
                run_id=args.run_id, model_key=args.model, concurrency=args.concurrency,
                game_mode=args.mode, max_cost_usd=args.max_cost_usd, prices=prices,
                metadata=proposal_metadata,
            ))
        except KeyboardInterrupt:
            rows = _run_rows(output, metadata)
            cost = sum(row.get("estimated_cost_usd_total") or 0 for row in rows)
            print(
                f"\nBenchmark interrupted.\n\nCompleted games: {len(rows)}/{len(games)}\n"
                f"Remaining games: {len(games) - len(rows)}\nCompleted-game cost recorded: ${cost:.2f}\n\n"
                f"Resume with the same command and --run-id:\n  {args.run_id}\n\n"
                f"Up to {args.concurrency} in-progress games may restart from round 1.", file=sys.stderr,
            )
            raise SystemExit(130)
        if len(_run_rows(output, metadata)) == len(games):
            _print_completion(output, metadata)
    elif args.command == "run-mock":
        config = yaml.safe_load(args.config.read_text())
        manifest_name = "dynamic" if args.condition is Condition.DYNAMIC_256 else "historical"
        manifest = Path(config["manifests"]) / f"dev_{manifest_name}.jsonl"
        game_id, state = load_game_states(
            manifest, args.condition, load_words(Path(config["answers"])),
            load_words(Path(config["extra_guesses"])),
            Path(config["historical_feedback_matrix"]),
        )[0]
        output = args.results / args.run_id
        output.mkdir(parents=True, exist_ok=True)
        models_path = Path("configs/models.yaml")
        metadata = _metadata(args.run_id, args.config, models_path, config,
                             "mock", {"provider": "mock", "model": "deterministic-secret"},
                             manifest, args.condition, args.mode, "dev", [game_id], 1)
        _resume_metadata(output / "metadata.json", metadata)
        removed, incomplete = clean_partial_proposals(
            output / "proposals.jsonl", output / "summaries.jsonl"
        )
        if removed:
            print(f"Resume cleanup: removed {removed} proposal rows from {incomplete} incomplete prior attempt{'s' if incomplete != 1 else ''}.")
        rows = _print_status(output, metadata, startup=True, concurrency=1)
        if len(rows) == 1:
            print("Run already complete: 1/1 games.\nNo provider calls required.")
            return
        alternatives = [word for word in state.legal_guesses if word != state.secret][:2]
        adapter = MockAdapter([[state.secret, *alternatives]])
        results = asyncio.run(run_batch(
            adapter, args.condition, [(game_id, state)], output / "proposals.jsonl",
            output / "summaries.jsonl", run_id=args.run_id, model_key="mock",
            game_mode=args.mode,
            metadata={"benchmark_version": BENCHMARK_VERSION, "prompt_version": PROMPT_VERSION,
                      "manifest_hash": _hash(manifest), "model_config_hash": _hash(models_path),
                      "provider": "mock", "requested_model_id": "deterministic-secret"},
        ))
        if len(_run_rows(output, metadata)) == 1:
            _print_completion(output, metadata)
    elif args.command == "analyze":
        output = args.output or args.results / "analysis"
        analyze_results(args.results, output, resamples=args.bootstrap_resamples, seed=args.seed)
        print(f"analysis written to {output}")
    elif args.command == "status":
        metadata_path = args.results / "metadata.json"
        if not metadata_path.exists():
            raise ValueError(f"missing {metadata_path}")
        _print_status(args.results, json.loads(metadata_path.read_text()))
    elif args.command == "clean-partials":
        removed, incomplete = clean_partial_proposals(
            args.results / "proposals.jsonl", args.results / "summaries.jsonl"
        )
        print(f"Removed {removed} orphan proposal rows from {incomplete} incomplete games.")
