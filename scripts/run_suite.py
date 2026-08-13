#!/usr/bin/env python3
"""Launch one complete OpenAI benchmark suite as resumable CLI runs."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from itertools import product
from pathlib import Path

from benchmark import BENCHMARK_VERSION

CONDITIONS = ("hist_named", "hist_unnamed", "dynamic_256")
MODES = ("normal", "strict")
SUITES = {
    "inference-dev": (("gpt4o", "gpt5", "gpt56"), "dev", Path("configs/models.yaml")),
    "inference-eval": (("gpt4o", "gpt5", "gpt56"), "eval", Path("configs/models.yaml")),
    "reasoning-dev": (("gpt5_medium", "gpt56_medium"), "dev", Path("configs/reasoning_models.yaml")),
    "reasoning-eval": (("gpt5_medium", "gpt56_medium"), "eval", Path("configs/reasoning_models.yaml")),
}


def commands(
    suite_name: str, *, results: Path, concurrency: int, dev_limit: int | None = None,
    max_cost_usd_per_run: float | None = None,
) -> list[list[str]]:
    models, split, models_config = SUITES[suite_name]
    if split == "eval" and dev_limit is not None:
        raise ValueError("--dev-limit cannot be used for an evaluation suite")
    result = []
    for model, condition, mode in product(models, CONDITIONS, MODES):
        treatment = "-medium" if model.endswith("_medium") else ""
        display_model = model.removesuffix("_medium")
        run_id = f"{display_model}-{condition}-{mode}{treatment}-{BENCHMARK_VERSION}-{split}-001"
        command = [
            sys.executable, "-m", "benchmark", "run",
            "--models-config", str(models_config), "--model", model,
            "--condition", condition, "--mode", mode, "--split", split,
            "--run-id", run_id, "--results", str(results),
            "--concurrency", str(concurrency),
        ]
        if dev_limit is not None:
            command += ["--limit", str(dev_limit)]
        if max_cost_usd_per_run is not None:
            command += ["--max-cost-usd", str(max_cost_usd_per_run)]
        result.append(command)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("suite", choices=SUITES)
    parser.add_argument("--results", type=Path, default=Path("results"))
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--dev-limit", type=int)
    parser.add_argument("--max-cost-usd-per-run", type=float)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.concurrency < 1 or (args.dev_limit is not None and args.dev_limit < 1):
        parser.error("concurrency and dev limit must be positive")

    try:
        suite_commands = commands(
            args.suite, results=args.results, concurrency=args.concurrency,
            dev_limit=args.dev_limit, max_cost_usd_per_run=args.max_cost_usd_per_run,
        )
    except ValueError as exc:
        parser.error(str(exc))
    print(f"Suite: {args.suite} | runs: {len(suite_commands)} | concurrency/run: {args.concurrency}")
    if args.dry_run:
        for command in suite_commands:
            print(" ".join(command))
        return
    if not os.environ.get("OPENAI_API_KEY"):
        parser.error("OPENAI_API_KEY is required")

    try:
        for index, command in enumerate(suite_commands, 1):
            print(f"\n=== Suite run {index}/{len(suite_commands)} ===", flush=True)
            subprocess.run(command, check=True)
    except KeyboardInterrupt:
        print("\nSuite interrupted. Rerun the same command to resume.", file=sys.stderr)
        raise SystemExit(130)


if __name__ == "__main__":
    main()
