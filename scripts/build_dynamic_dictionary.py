from __future__ import annotations

import argparse
import gzip
from pathlib import Path

from wordfreq import iter_wordlist

from benchmark.experiment.manifests import load_words


def build(scowl_path: Path, answers_path: Path) -> tuple[str, ...]:
    opener = gzip.open if scowl_path.suffix == ".gz" else open
    with opener(scowl_path, "rt") as source:
        scowl = {word.lower() for line in source if (word := line.strip()).isascii() and word.isalpha() and len(word) == 5}
    common = {word for word in iter_wordlist("en", "small") if word.isascii() and word.isalpha() and len(word) == 5}
    answers = set(load_words(answers_path))
    return tuple(sorted(scowl & common - answers))


def write_dictionary(path: Path, words: tuple[str, ...], force: bool = False) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"{path} exists; pass --force to overwrite")
    path.write_text("\n".join(words) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scowl", type=Path, required=True)
    parser.add_argument("--answers", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        write_dictionary(args.output, build(args.scowl, args.answers), args.force)
    except FileExistsError as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
