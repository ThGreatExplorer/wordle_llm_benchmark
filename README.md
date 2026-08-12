# Wordle LLM Benchmark

A reproducible Python benchmark for studying **multi-turn lexical constraint reasoning** in language models using controlled Wordle-style environments.

The project compares frontier, legacy, and open-weight models on their ability to:

- maintain hard letter/position constraints across turns;
- generate legal candidate guesses;
- choose strategically informative guesses;
- rank strong candidates among their top three suggestions; and
- recover from an invalid guess after one explicit verifier rejection.

The benchmark is intentionally more than a Wordle leaderboard. Wordle is used as a deterministic environment for studying constraint tracking, lexical reasoning, information seeking, ranking, and self-correction.

> **Implementation note:** `DESIGN.md` is the canonical experiment specification. `AGENTS.md` contains coding-agent instructions. If you are using Codex, give it both files before asking it to implement the project.

---

## Research questions

**RQ1.** How does multi-turn word-constraint reasoning vary across frontier, legacy, and open-weight language models?

**RQ2.** How much does recognizing the task as Wordle improve performance?

**RQ3.** Does changing Wordle from a fixed historical answer distribution to dynamically generated candidate spaces reduce frontier-model saturation?

---

## Experimental conditions

The frozen MVP contains three conditions.

| Condition | Task name exposed? | Secret universe | Legal guesses | Evaluation games |
|---|---|---|---|---:|
| `hist_named` | Yes — Wordle | Original 2022 Wordle solution list | Original 2022 Wordle legal-guess list | 150 |
| `hist_unnamed` | No | Same historical solution list | Same historical legal-guess list | 150 |
| `dynamic_256` | No | Fresh frozen 256-word pool per instance | Exactly those same 256 words | 150 |

`hist_named` and `hist_unnamed` use the **same 150 secrets**, allowing a paired comparison that isolates the effect of recognizing the game as Wordle.

`dynamic_256` contains 150 independently generated and frozen candidate pools. Each model receives the exact same pools, secrets, and candidate ordering.

There are six primary model tracks:

- GPT-4o
- GPT-5
- GPT-5.6
- Qwen3 8B
- Qwen3 14B
- Qwen3 32B

The complete evaluation therefore contains:

```text
6 models × 3 conditions × 150 games = 2,700 games
```

Separate development manifests are used for debugging and provider integration before the evaluation manifests are touched.

---

## Core game protocol

Each game has at most **six decision rounds**.

On every normal round, the benchmark constructs a fresh prompt from:

1. the game rules;
2. condition-specific instance information; and
3. the complete accepted public guess/feedback history.

The model returns its **top three ranked guesses**.

Only guess #1 is used as the proposed game action. Guesses #2 and #3 are recorded for behavioral analysis but are not inserted into the next normal-turn prompt.

The benchmark validates the proposed top-1 guess locally.

Possible outcomes are:

```text
FORMAT_ERROR
LEXICON_ERROR
CONSTRAINT_ERROR
VALID
```

If the initial top-1 guess is invalid, the model receives exactly **one repair attempt** containing the error class but not the exact violated clue.

If the repair is valid, it becomes the round's accepted guess. If the repair is still invalid, that decision round is forfeited.

The benchmark never silently replaces an invalid top-1 guess with guess #2 or guess #3.

---

## Stateless model evaluation

LLM conversation state is deliberately not persisted.

Every turn is a new model request containing the reconstructed public game state. Provider-side conversation IDs, prior response IDs, or equivalent session mechanisms must not be used by the benchmark core.

This ensures that:

- games cannot leak information into one another;
- provider-specific conversation implementations do not affect the benchmark;
- every model is evaluated from the same explicit observable state.

Infrastructure retries such as HTTP timeouts are distinct from experimental repair attempts. A transport retry does not count as a model error; an invalid word does.

---

## Deterministic local evaluator

The Python benchmark is authoritative for:

- Wordle feedback;
- repeated-letter semantics;
- legal-word validation;
- hard-mode constraint consistency;
- feasible candidate sets;
- information gain;
- game state;
- win/loss status;
- experiment metrics.

Models are never asked to grade themselves.

### Feedback labels

All conditions use the same neutral labels:

- `EXACT` — correct letter in the correct position;
- `PRESENT` — the letter occurs in another still-unmatched position;
- `ABSENT` — no unmatched occurrence of that letter remains.

The scorer uses standard two-pass Wordle duplicate-letter handling: exact matches are consumed first, followed by remaining misplaced matches.

A candidate word is hard-mode-consistent with the history when it would reproduce every feedback pattern already observed:

```python
all(
    score(candidate, previous_guess) == previous_feedback
    for previous_guess, previous_feedback in history
)
```

---

## Dynamic vocabulary

The dynamic benchmark uses a frozen five-letter vocabulary built from:

1. SCOWL level 60 American English;
2. intersected with the `wordfreq` small/common English vocabulary;
3. filtered to lowercase ASCII alphabetic words of length five; and
4. with the original historical Wordle answer list removed.

The resulting master vocabulary is generated once, normalized, hashed, and frozen.

Each `dynamic_256` game samples 256 unique words from this master vocabulary. The secret is selected from that same pool. The full materialized pool and secret are stored in the manifest and reused across every model.

Benchmark execution does **not** regenerate pools dynamically.

---

## Main metrics

### Primary outcome metrics

**Solve@6**

Fraction of games solved within six decision rounds.

**Mean decision-round score**

Solved games receive the round in which they were solved; unsolved games receive a score of 7.

This prevents a model with many failures from looking artificially efficient when averaging only successful games.

### Constraint fidelity

**Valid@1** — fraction of initial top-ranked proposals that satisfy all format, lexicon, and historical constraints.

**Valid@3** — fraction of all three suggestions that are valid under the current state.

### Strategic quality

For every state, the deterministic solver computes expected information gain for every currently legal guess.

This supports:

- normalized information efficiency;
- search regret — whether the model failed to generate a strong guess anywhere in its top three;
- ranking regret — whether the model generated a stronger option but ranked a weaker one first.

### Multi-turn constraint retention

When a guess contradicts prior feedback, the evaluator records the age of the violated clue. This allows analysis of constraint-violation rate as previously established information becomes older across turns.

### Self-correction

The benchmark records:

- repair success rate;
- repair success by error type;
- failed-repair / round-forfeit rate.

No arbitrary weighted composite score is used in the MVP.

---

## Project structure

The intended repository layout is:

```text
wordle-llm-benchmark/
├── README.md
├── DESIGN.md
├── AGENTS.md
├── pyproject.toml
├── uv.lock
├── .env.example
│
├── configs/
│   ├── benchmark.yaml
│   └── models.yaml
│
├── data/
│   ├── README.md
│   ├── raw/
│   ├── frozen/
│   │   ├── wordle_answers_2022.txt
│   │   ├── wordle_extra_guesses_2022.txt
│   │   └── dynamic_master_5letter.txt
│   └── manifests/
│       ├── dev_historical.jsonl
│       ├── dev_dynamic.jsonl
│       ├── eval_historical.jsonl
│       └── eval_dynamic.jsonl
│
├── benchmark/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py
│   ├── types.py
│   ├── engine/
│   ├── prompts/
│   ├── providers/
│   ├── experiment/
│   └── analysis/
│
├── scripts/
│   └── build_dynamic_dictionary.py
│
├── tests/
└── results/
```

See `DESIGN.md` for the detailed module responsibilities.

## Running a provider development slice

Install dependencies with `uv sync`, copy `.env.example` to your environment, and
set the relevant API key. Provider calls happen only through the explicit `run`
command:

```bash
uv run python -m benchmark run \
  --model gpt4o \
  --condition hist_named \
  --split dev \
  --run-id dev-gpt4o \
  --concurrency 1 \
  --max-cost-usd 1
```

For Qwen, set `OPENROUTER_API_KEY`. The frozen Qwen3 8B, 14B, and 32B tracks use
OpenRouter's OpenAI-compatible endpoint; local model serving is not part of this
benchmark. Each request is stateless, and the runner never passes a conversation
or previous-response ID.

Results are append-only JSONL under `results/<run-id>/`. Reusing the same run ID
skips completed model/condition/game keys and rejects changed run metadata.
Because usage is known only after a response, concurrent cost guarding can exceed
the limit by at most one batch (`--concurrency` games); use concurrency 1 for the
tightest budget control.

---

## Requirements

- Python 3.11 or newer
- [`uv`](https://docs.astral.sh/uv/)
- API credentials only for providers you intend to run
- OpenRouter account and API key for the Qwen tracks

The project uses `uv` for dependency management, virtual environments, locking, and command execution.

---

## Setup

Clone the repository and create/sync the environment:

```bash
git clone <repository-url>
cd wordle-llm-benchmark
uv sync
```

Run the deterministic test suite:

```bash
uv run pytest
```

The test suite must not make paid API calls by default.

If the repository provides an example environment file:

```bash
cp .env.example .env
```

Add only the credentials needed for the provider adapters you intend to use. Do not commit `.env` or API keys.

---

## Dependency management

Add runtime dependencies with:

```bash
uv add <package>
```

Add development/test dependencies with:

```bash
uv add --dev <package>
```

After dependency changes, commit both:

```text
pyproject.toml
uv.lock
```

Do not use separate Conda/Poetry/Pipenv environments for this project.

---

## Development workflow

The implementation should proceed in this order.

### 1. Deterministic engine

Build and test scoring, duplicate-letter semantics, candidate filtering, constraints, and information gain.

```bash
uv run pytest tests/test_feedback.py tests/test_duplicates.py
```

### 2. Frozen data pipeline

Validate historical word lists, construct/freeze the dynamic dictionary, and generate development/evaluation manifests.

Conceptually:

```bash
uv run python scripts/build_dynamic_dictionary.py ...
uv run python -m benchmark generate-manifests --config configs/benchmark.yaml
```

Do not regenerate evaluation manifests during normal benchmark runs.

### 3. Prompts + mock provider

Implement all three prompt variants, output parsing, error classification, one-repair semantics, and end-to-end games using a deterministic mock model.

```bash
uv run python -m benchmark run \
  --config configs/benchmark.yaml \
  --models mock \
  --mode dynamic_256 \
  --split dev
```

### 4. Provider integration

Only after deterministic and mock tests pass, connect real providers.

The benchmark needs two main adapter styles:

- OpenAI Responses API;
- OpenRouter's OpenAI-compatible endpoint for Qwen inference.

Provider-specific model IDs, endpoints, prices, and reasoning settings belong in configuration rather than game code.

### 5. Analysis

Aggregate completed runs and produce the predefined metrics and confidence intervals.

```bash
uv run python -m benchmark analyze --results results/<run-id>
```

---

## Running experiments

The final CLI may differ slightly during implementation, but it should support workflows equivalent to the following.

### Run one development condition

```bash
uv run python -m benchmark run \
  --config configs/benchmark.yaml \
  --models gpt-4o \
  --mode hist_named \
  --split dev
```

### Run dynamic development games

```bash
uv run python -m benchmark run \
  --config configs/benchmark.yaml \
  --models qwen3-8b \
  --mode dynamic_256 \
  --split dev
```

### Apply a cost guard

```bash
uv run python -m benchmark run \
  --config configs/benchmark.yaml \
  --models gpt-4o \
  --mode hist_named \
  --split dev \
  --max-cost-usd 2
```

### Analyze a completed run

```bash
uv run python -m benchmark analyze --results results/<run-id>
```

Do not start the 150-game evaluation split until development runs, prompt checks, manifest hashes, and deterministic tests are frozen and passing.

---

## Model configuration

Exact model identifiers should not be hard-coded into benchmark logic.

A configuration file such as `configs/models.yaml` should define each experiment model's:

- logical benchmark name;
- provider adapter;
- provider model ID;
- endpoint/base URL where applicable;
- reasoning/thinking mode;
- generation settings;
- maximum output tokens;
- input/output pricing used for cost accounting.

This keeps the experiment protocol stable even when provider deployment details change.

For the primary benchmark, use direct/non-thinking or the lowest practical reasoning mode consistently enough to avoid intentionally assigning radically different inference-time reasoning budgets across model families. Record the actual settings with every run.

---

## Qwen execution

Qwen models run through OpenRouter's hosted OpenAI-compatible API. Local serving
and other aggregators are outside the frozen benchmark protocol.

The frozen Qwen scaling comparison is Qwen3 8B → 14B → 32B, with all three routed through OpenRouter. Qwen3 4B is excluded because it is unavailable in the selected deployment.

---

## Reproducibility

Every run should record enough metadata to reconstruct how it was produced, including:

```text
run ID
git commit
benchmark version
prompt version
manifest hashes
word-list hashes
models config hash
benchmark config hash
Python version
uv.lock hash
provider/model identifiers
pricing configuration
host/platform metadata
```

For OpenRouter Qwen runs, also record requested and returned model identifiers, routing/provider metadata when available, pricing configuration, and reasoning mode.

Raw results should be treated as immutable experiment artifacts. Analysis should read raw logs and write derived tables/figures separately rather than mutating the original records.

---

## Development vs. evaluation data

The repository contains separate development and evaluation manifests.

Development data is for:

- API debugging;
- prompt verification;
- parser development;
- cost estimation;
- concurrency tuning;
- local end-to-end testing.

The final evaluation data is not for iterative prompt optimization.

Once evaluation prompts/manifests are frozen, changes that affect experimental semantics require a version bump and rerunning all affected model comparisons.

---

## Testing requirements

Research-critical behavior must be tested locally.

At minimum, tests should cover:

- exact/present/absent scoring;
- repeated-letter edge cases;
- candidate consistency against full history;
- historical vs. dynamic legal-guess rules;
- information gain on tiny enumerable candidate sets;
- prompt contamination checks;
- session isolation;
- repair and failed-repair behavior;
- manifest sizes and uniqueness;
- manifest reproducibility;
- complete mock-provider games.

Run everything with:

```bash
uv run pytest
```

Real provider tests should be explicitly opt-in and should never run during an ordinary `pytest` invocation.

---

## Result outputs

The benchmark should retain two levels of records.

### Proposal-level data

One record for every initial or repair model response, including:

- top-three guesses;
- validity/error category for each;
- round/state metadata;
- candidate count;
- information-gain metrics;
- token usage;
- latency;
- cost;
- model/prompt/config identifiers.

### Game-level summaries

One row per model × condition × game containing at least:

- solved/not solved;
- solve round;
- decision-round score;
- accepted-guess count;
- repair count;
- repair successes;
- forfeits.

Prefer Parquet for analysis-friendly outputs and JSONL where an inspectable append-only representation is useful.

---

## Analysis strategy

### RQ1 — model capability

Compare all six models on task success, constraint fidelity, information efficiency, ranking/search regret, constraint-age errors, and repair behavior.

For Qwen, parameter count provides a natural scaling axis. For OpenAI models, treat GPT-4o → GPT-5 → GPT-5.6 as a model-generation comparison rather than a parameter-count curve.

### RQ2 — Wordle recognition

Use the paired contrast:

```text
hist_named - hist_unnamed
```

Because the two conditions share the same 150 secrets, calculate seed-paired effects and confidence intervals.

### RQ3 — dynamic generalization

Compare:

```text
hist_unnamed vs. dynamic_256
```

rather than `hist_named` vs. `dynamic_256`, so task-name recognition is not deliberately mixed into this comparison.

This is a generalization/validation comparison rather than a perfectly isolated one-variable ablation, because the dynamic condition deliberately changes the candidate universe and its presentation.

---

## Optional post-MVP extension

Fine-tuning is outside the MVP and is not specified for the frozen six-model benchmark.

Evaluate the fine-tuned model on:

1. unseen dynamic pools; and
2. unseen dynamic pools with arbitrary replacements for the `EXACT`, `PRESENT`, and `ABSENT` labels.

This extension asks whether fine-tuning learns transferable constraint reasoning rather than merely memorizing Wordle-specific vocabulary or surface labels.

Any future fine-tuning study must not alter the primary six-model RQ1–RQ3 benchmark.

---

## For Codex

Start by reading:

```text
DESIGN.md
AGENTS.md
README.md
```

Then inspect the repository and implement **Milestones 1–3 before provider integration**.

Do not spend API money until:

- deterministic engine tests pass;
- frozen manifests work;
- prompt contamination tests pass;
- mock-provider full games pass;
- repair/forfeit semantics are verified.

Provider SDK changes may require updating adapter/configuration code. They do **not** justify changing the frozen experimental protocol.
