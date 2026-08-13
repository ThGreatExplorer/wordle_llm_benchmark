# Wordle LLM Benchmark

A contamination-resistant benchmark for multi-turn lexical constraint tracking in
language models.

Modern LLMs can solve difficult coding and mathematics tasks, but those successes
can be difficult to separate from learned patterns, tool use, or benchmark
familiarity. Wordle offers a simpler, auditable test: can a model carry forward a
small set of positional, membership, exclusion, and duplicate-letter constraints
over several turns?

This repository contains the deterministic game engine, frozen manifests, stateless
provider harness, analysis pipeline, and Observable Framework results portal used in
the final project report:

> **Do LLMs Actually Reason About Wordle?**
>
> *A Contamination-Resistant Benchmark for Multi-Turn Constraint Tracking*

The complete report is available in
[`wordle_llm_benchmark_final_report_with_results.docx`](wordle_llm_benchmark_final_report_with_results.docx).

## Research questions

1. How does multi-turn word-constraint reasoning vary across frontier and legacy
   language models?
2. How much does recognizing the task as Wordle improve performance?
3. Does replacing the historical answer distribution with dynamically generated
   candidate spaces reduce frontier-model saturation?
4. How does explicit inference-time reasoning effort change performance?

## Part 1 MVP

The completed Part 1 MVP compares three OpenAI model tracks:

- GPT-4o
- GPT-5
- GPT-5.6

Each model is evaluated on 150 frozen games in three conditions:

| Condition | Task name exposed? | Secret universe | Legal guesses |
|---|---|---|---|
| `hist_named` | Yes | Original 2022 Wordle answers | Original historical legal-guess set |
| `hist_unnamed` | No | Same 150 historical secrets | Same historical legal-guess set |
| `dynamic_256` | No | Frozen 256-word pool per game | Exactly that game's 256 words |

The primary normal-mode matrix contains:

```text
3 models × 3 conditions × 150 games = 1,350 games
```

The harness also supports `strict` mode as a separate constraint-enforced
experiment. Qwen3 8B, 14B, and 32B are deferred to Part 2 and are not part of MVP
coverage or primary conclusions.

## Protocol in brief

Every model call is stateless. Each turn reconstructs the complete public game state
from the rules and played history; provider conversation state is never reused.

The model returns three ranked guesses:

- top-1 is the proposed action;
- top-2 and top-3 are diagnostics only;
- an invalid top-1 receives exactly one repair attempt;
- top-2/top-3 are never automatically promoted.

Action validity and constraint consistency are measured separately:

- **Action-valid** means structurally and lexically playable.
- **Constraint-consistent** means exact replay against every previous feedback row.

In `normal` mode, every action-valid top-1 is played even if it violates an earlier
clue. The violation is recorded and deterministic feedback is still returned.

In `strict` mode, constraint inconsistency blocks play and triggers the one permitted
repair. Failed repair forfeits the decision round without feedback.

The local Python engine is authoritative for duplicate-aware feedback, legality,
constraint replay, feasible-secret filtering, and information gain. See
[`DESIGN.md`](DESIGN.md) for the full experimental specification.

## Final normal-mode results

All 1,350 primary normal-mode games are complete. Solve@6 results from the final
report are:

| Model | Historical named | Historical unnamed | Dynamic 256 |
|---|---:|---:|---:|
| GPT-4o | 3.3% | 6.0% | 8.7% |
| GPT-5 | 6.7% | 6.0% | 6.0% |
| GPT-5.6 | 58.7% | 55.3% | 66.7% |

Selected behavioral metrics:

| Model | Hist-named CC@1 | Hist-named IG efficiency | Dynamic Action Valid@1 |
|---|---:|---:|---:|
| GPT-4o | 20.9% | 0.624 | 79.8% |
| GPT-5 | 24.8% | 0.637 | 57.9% |
| GPT-5.6 | 49.7% | 0.765 | 83.3% |

### Main findings

- **GPT-5.6 is a discontinuous improvement.** Its paired Solve@6 advantage over
  GPT-5 is 49.3–60.7 percentage points across conditions. GPT-5 does not materially
  outperform GPT-4o.
- **Constraint tracking is the central bottleneck.** GPT-4o and GPT-5 historical
  consistency falls to roughly 3–7% by round 3 and approaches zero in later rounds.
  GPT-5.6 is substantially better but remains imperfect.
- **Naming Wordle does not reliably help.** GPT-5 and GPT-5.6 have no statistically
  clear naming effect. GPT-4o performs 2.7 percentage points worse when named, the
  opposite of the expected direction.
- **Dynamic does not automatically mean harder.** GPT-5.6 performs best in the
  dynamic condition. The unfamiliar vocabulary increases legality errors, but the
  256-word secret space also makes search easier.
- **GPT-5 is unusually poor at dynamic-pool compliance.** Its dynamic Action
  Valid@1 is 57.9%, more than half of logged suggestions are outside the supplied
  pool, and its repeated-guess rate reaches 15.6%.
- **Strict enforcement creates feedback starvation.** Complete GPT-5 strict runs
  forfeit more than four rounds per game. In the provisional 96-game GPT-5.6 dynamic
  comparison, strict enforcement reduces Solve@6 by 28.1 points (95% CI 17.7–38.5).

Strict evaluation is incomplete for GPT-4o and GPT-5.6, and medium-reasoning
evaluation results were not available for the final report. Do not treat those
comparisons as final. A detailed machine-oriented handoff is stored at
[`results/analysis-openai-eval/TECHNICAL_RESULTS_HANDOFF.md`](results/analysis-openai-eval/TECHNICAL_RESULTS_HANDOFF.md).

## Requirements

- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/)
- Node.js and npm for the results portal
- `OPENAI_API_KEY` only when making paid OpenAI calls

Install the Python environment:

```bash
uv sync
```

Install frontend dependencies:

```bash
cd frontend
npm install
cd ..
```

No provider calls occur during imports, deterministic tests, manifest generation,
analysis, or portal use.

## Validate the deterministic benchmark

Run the full deterministic suite:

```bash
uv run pytest
```

Useful CLI discovery:

```bash
uv run python -m benchmark --help
uv run python -m benchmark run --help
uv run python -m benchmark analyze --help
```

Generate manifests only when intentionally rebuilding them:

```bash
uv run python -m benchmark generate-manifests \
  --config configs/benchmark.yaml
```

Frozen dictionary and manifest generation refuses overwrites unless explicitly
given `--force`.

## Run experiments

### One development run

```bash
uv run python -m benchmark run \
  --model gpt4o \
  --condition hist_named \
  --mode normal \
  --split dev \
  --run-id gpt4o-hist-named-normal-dev \
  --concurrency 1 \
  --max-cost-usd 1
```

Each result directory contains frozen run metadata plus append-only proposal and
summary JSONL files. Reusing the exact command and `--run-id` resumes at whole-game
granularity:

- completed games are skipped;
- interrupted in-progress games restart from round 1;
- summaries are the durable completion markers;
- orphan proposals are excluded from analysis and cleaned on resume.

Check a run without making provider calls:

```bash
uv run python -m benchmark status \
  --results results/gpt4o-hist-named-normal-dev
```

Use `--force-resume` only when knowingly accepting metadata drift. It preserves the
checkpoint but does not make incompatible experimental configurations comparable.

### Complete OpenAI suites

The suite launcher expands a selection into separate sequential, resumable runs:

```bash
# Inspect commands only.
uv run python scripts/run_suite.py inference-eval --dry-run

# Run the primary OpenAI inference suite.
uv run python scripts/run_suite.py inference-eval \
  --concurrency 4 \
  --max-cost-usd-per-run 10
```

Supported suite names:

- `inference-dev`
- `inference-eval`
- `reasoning-dev`
- `reasoning-eval`

Reasoning suites include only GPT-5 and GPT-5.6 with medium reasoning. Development
and evaluation results must be analyzed separately.

## Analyze results

Generate the canonical OpenAI evaluation snapshot:

```bash
uv run python -m benchmark analyze \
  --results results \
  --output results/analysis-openai-eval \
  --provider openai \
  --split eval
```

Analyze medium-reasoning development runs separately:

```bash
uv run python -m benchmark analyze \
  --results results \
  --output results/analysis-openai-reasoning-dev \
  --provider openai \
  --split dev \
  --model-prefix gpt5_medium \
  --model-prefix gpt56_medium
```

The deterministic analysis pipeline:

- reads only games with durable completed summaries;
- ignores orphan proposals;
- rejects duplicate completed summaries;
- computes aggregate behavioral metrics;
- performs 10,000 game-level bootstrap resamples by default;
- pairs comparisons by exact game ID when appropriate;
- records incomplete coverage and pair counts explicitly;
- emits Parquet as the canonical processed representation and CSV mirrors for
  convenience.

Core processed outputs include:

```text
metrics.parquet
run_coverage.parquet
games.parquet
proposals.parquet
analysis_metadata.json

contrasts/
  paired.parquet
  model.parquet
  dynamic.parquet
  reasoning.parquet
  enforcement_penalty.parquet
  penalty_reduction.parquet

diagnostics/
  constraint_age.parquet
  consistency_by_round.parquet
```

## Results portal

Python owns scientific analysis. Parquet is the frontend-neutral contract.
Observable Framework owns only presentation, filtering, and client-side DuckDB-Wasm
queries.

Launch the default evaluation snapshot:

```bash
cd frontend
npm run dev
```

Use another processed snapshot:

```bash
cd frontend
WORDLE_ANALYSIS_DIR=../results/analysis-openai-reasoning-dev npm run dev
```

The portal has three routes:

- **Research Report** — editorial summary, primary contrasts, findings, caveats,
  compute analysis, and provenance.
- **Experiment Lab** — coordinated filters, metric explanations, model/condition
  comparisons, contrast forest plots, constraint diagnostics, and coverage status.
- **Game Inspector** — searchable completed games, Wordle feedback board,
  candidate-space trajectory, ranked top-three diagnostics, oracle information gain,
  repairs, tokens, latency, and cost.

Build a self-contained static site:

```bash
cd frontend
npm run build
```

The portal is read-only. It does not parse raw benchmark JSONL, make provider calls,
modify results, or recompute statistical estimates.

## Repository layout

```text
benchmark/             deterministic engine, providers, runner, analysis
configs/               benchmark and model configurations
data/                  provenance, frozen vocabularies, manifests
analysis/interpretation/ human-authored metric definitions/findings/caveats
frontend/              Observable Framework portal
scripts/               data/provider probes and suite launcher
tests/                 deterministic Python tests
results/               raw run directories and processed analysis snapshots
DESIGN.md              canonical experimental specification
AGENTS.md              coding-agent rules and invariants
```

## Reproducibility and safety

Runs record the benchmark and prompt versions, exact model and provider settings,
manifest/config hashes, selected game IDs, reasoning settings, temperature, token
caps, timeout, Git commit, token usage, latency, and estimated cost where available.

Use development manifests for debugging. Do not tune prompts or protocol behavior
after inspecting evaluation results. Never commit provider credentials. Paid calls
must remain explicit and should use `--max-cost-usd` where pricing is configured.

## Part 2: Qwen extension

Qwen is not part of the Part 1 MVP. Existing Hugging Face/Nscale adapter and model
configuration code is retained for a later Part 2 comparison of Qwen3 8B, 14B, and
32B. Part 2 must explicitly pin Nscale through the `:nscale` model suffix, use
stateless requests and strict structured output, and establish its own complete
coverage before Qwen results enter any comparative claims.

## References

- Abdulhai et al., [“LMRL Gym: Benchmarks for Multi-Turn Reinforcement Learning
  with Language Models”](https://proceedings.mlr.press/v267/abdulhai25a.html),
  ICML 2025.
- Liu, [“Wordle Arena for LLMs”](https://drchangliu.github.io/WordleArena/), 2026.
- Atkinson, [SCOWL](https://wordlist.aspell.net/).
- Speer, [`wordfreq`](https://github.com/rspeer/wordfreq).

## License and attribution

This repository contains an individual research project by Daniel Yu. See the final
report for the complete methodology, interpretation, limitations, references, and
AI-use acknowledgment.
