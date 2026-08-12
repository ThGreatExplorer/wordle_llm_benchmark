from __future__ import annotations

import argparse
from pathlib import Path

from benchmark.engine.information import write_feedback_matrix
from benchmark.experiment.manifests import load_words


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--answers", type=Path, default=Path("data/frozen/wordle_answers_2022.txt"))
    parser.add_argument("--extra-guesses", type=Path, default=Path("data/frozen/wordle_extra_guesses_2022.txt"))
    parser.add_argument("--output", type=Path, default=Path("data/frozen/historical_feedback.bin"))
    args = parser.parse_args()
    answers = load_words(args.answers)
    legal = tuple(dict.fromkeys((*answers, *load_words(args.extra_guesses))))
    write_feedback_matrix(args.output, legal, answers)


if __name__ == "__main__":
    main()
