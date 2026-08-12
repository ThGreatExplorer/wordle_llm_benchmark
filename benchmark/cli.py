from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from benchmark.experiment.manifests import generate_manifests, load_words


def main() -> None:
    parser = argparse.ArgumentParser(prog="wordle-llm-benchmark")
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate = subparsers.add_parser("generate-manifests")
    generate.add_argument("--config", type=Path, default=Path("configs/benchmark.yaml"))
    args = parser.parse_args()
    if args.command == "generate-manifests":
        config = yaml.safe_load(args.config.read_text())
        hashes = generate_manifests(
            load_words(Path(config["answers"])), load_words(Path(config["dynamic_vocabulary"])),
            Path(config["manifests"]), config["master_seed"],
        )
        for name, digest in hashes.items():
            print(f"{name}: {digest}")
