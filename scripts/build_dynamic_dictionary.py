from __future__ import annotations

import argparse
import gzip
from pathlib import Path

from wordfreq import iter_wordlist

from benchmark.experiment.manifests import load_words
from benchmark.prompts.builders import BANNED


def build(scowl_path: Path, answers_path: Path) -> tuple[str, ...]:
    opener = gzip.open if scowl_path.suffix == ".gz" else open
    with opener(scowl_path, "rt") as source:
        scowl = {word.lower() for line in source if (word := line.strip()).isascii() and word.isalpha() and len(word) == 5}
    common = {word for word in iter_wordlist("en", "small") if word.isascii() and word.isalpha() and len(word) == 5}
    answers = set(load_words(answers_path))
    return tuple(sorted(word for word in scowl & common - answers if not any(term in word for term in BANNED)))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scowl", type=Path, required=True)
    parser.add_argument("--answers", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text("\n".join(build(args.scowl, args.answers)) + "\n")


if __name__ == "__main__":
    main()
