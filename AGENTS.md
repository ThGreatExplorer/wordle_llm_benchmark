# AGENTS.md

## Purpose

This repository implements a reproducible benchmark for multi-turn lexical constraint reasoning in language models using three Wordle-style conditions.

`DESIGN.md` is the canonical specification for the experiment. Read it completely before making substantive changes.

This file defines how coding agents should work in the repository. If this file and `DESIGN.md` appear to conflict:

1. preserve the experimental protocol in `DESIGN.md`;
2. preserve deterministic/reproducible behavior;
3. choose the simplest implementation that satisfies both;
4. ask before changing any frozen experimental decision.

Do not reinterpret the research design for convenience.

---

## Technology choices

- Language: Python 3.11+
- Package/environment manager: `uv`
- Test runner: `pytest`
- Configuration: YAML where appropriate
- Structured experiment output: JSONL and/or Parquet
- Source layout: package named `benchmark/`

Use `uv` for all dependency and execution workflows. Do not introduce Poetry, Pipenv, Conda, or ad-hoc `pip install` instructions.

Typical commands:

```bash
uv sync
uv run pytest
uv run pytest tests/test_feedback.py -q
uv run python -m benchmark --help
uv add <package>
uv add --dev <package>
```

If linting/type-checking tools are added, run them through `uv run` as well.

Keep `uv.lock` committed once dependencies are established.

---

## Canonical project documents

Before implementing, inspect at minimum:

```text
DESIGN.md
AGENTS.md
README.md
pyproject.toml
configs/
data/README.md          # once present
```

Responsibilities:

- `DESIGN.md`: experimental design and frozen benchmark semantics.
- `AGENTS.md`: coding-agent behavior and implementation constraints.
- `README.md`: human-facing setup and usage.
- `configs/`: model/provider/run configuration.
- `data/README.md`: word-list provenance, normalization, hashes, and manifest metadata.

Do not duplicate large portions of `DESIGN.md` into code comments. Link concepts through names and concise comments instead.

---

## Experimental invariants: do not change silently

The MVP consists of exactly six model tracks:

- GPT-4o
- GPT-5
- GPT-5.6
- Qwen3 8B
- Qwen3 14B
- Qwen3 32B

and exactly three evaluation conditions:

- `hist_named`
- `hist_unnamed`
- `dynamic_256`

with 150 frozen evaluation games per condition per model.

Important invariants include:

- `hist_named` and `hist_unnamed` use the same 150 historical secrets.
- `dynamic_256` uses 150 frozen candidate pools.
- Each dynamic pool has exactly 256 unique five-letter words.
- In `dynamic_256`, the candidate pool is also the complete legal-guess universe.
- Each game has at most six decision rounds.
- The game uses strict Wordle-hard-mode-style constraint satisfaction.
- Every normal LLM turn is reconstructed from rules + complete accepted public history.
- Provider conversation/session state must not persist between turns or games.
- Previous top-2/top-3 suggestions are measurements and must not be inserted into later normal-turn prompts.
- An invalid top-1 guess receives exactly one repair attempt.
- A failed repair forfeits that decision round.
- Do not automatically promote guess #2 or #3 when guess #1 is invalid.
- The local deterministic engine is authoritative for scoring, validity, candidate filtering, and information gain.
- The same feedback semantics (`EXACT`, `PRESENT`, `ABSENT`) are used in all three conditions.
- Unnamed conditions must not leak Wordle-specific names or conventional color terminology.
- Evaluation manifests and prompts are frozen before final model evaluation.

If a requested code change would alter one of these invariants, stop and surface the conflict rather than silently implementing it.

---

## Implementation priorities

Follow the milestone order from `DESIGN.md`.

### Milestone 1 — deterministic core

Implement and test:

- Wordle feedback/scoring;
- duplicate-letter semantics;
- game state;
- strict constraint validation;
- feasible-candidate filtering;
- information-gain computation.

This must be correct before any paid API integration.

### Milestone 2 — frozen data pipeline

Implement and test:

- historical word-list validation;
- SCOWL + `wordfreq` dynamic vocabulary construction;
- stable seed derivation;
- development/evaluation manifest generation;
- hashes/provenance.

Benchmark execution must consume fully materialized frozen manifests. It must not regenerate candidate pools during a run.

### Milestone 3 — prompts and mock harness

Implement and test:

- named historical prompt;
- unnamed historical prompt;
- dynamic-256 prompt;
- top-three response parsing;
- validation/error taxonomy;
- one-repair protocol;
- detailed proposal logging;
- game summaries;
- deterministic mock-provider end-to-end tests.

### Milestone 4 — providers

Only after Milestones 1–3 pass:

- OpenAI Responses API adapter;
- OpenRouter adapter through its OpenAI-compatible endpoint for Qwen;
- token/latency/cost capture;
- transient retry handling;
- bounded concurrency;
- resume support.

### Milestone 5 — analysis

Implement:

- Solve@6;
- mean decision-round score with failures scored as 7;
- Valid@1;
- Valid@3;
- information efficiency;
- search regret;
- ranking regret;
- repair success / forfeit rate;
- constraint violation by constraint age;
- paired bootstrap confidence intervals;
- simple reproducible tables/plots.

Fine-tuning is post-MVP only.

---

## Repository structure

Prefer the structure specified in `DESIGN.md`:

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
│   └── manifests/
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
├── tests/
└── results/
```

Small deviations are acceptable if they improve clarity, but do not collapse experimental logic into one monolithic script.

---

## Python coding guidelines

Prefer straightforward, typed Python over abstraction-heavy framework code.

Use:

- `dataclasses` or small typed models for domain records;
- `Enum`/`Literal` for closed categories such as feedback and error types;
- `pathlib.Path` for filesystem paths;
- `asyncio` for concurrent remote inference where useful;
- explicit dependency injection for providers/configuration;
- pure functions for scoring, filtering, and information calculations wherever practical.

Avoid:

- global mutable game state;
- provider-specific logic inside the game engine;
- hidden network calls in constructors/imports;
- nondeterministic iteration where output order matters;
- Python's built-in `hash()` for reproducible seeds;
- silently swallowing invalid model responses;
- parsing logic that “fixes” model output before metrics are recorded;
- premature framework adoption.

Public functions/classes should have type hints. Add docstrings where behavior or invariants are non-obvious; do not add boilerplate docstrings that merely restate names.

---

## Determinism requirements

Determinism is a first-class requirement for everything except model inference itself.

Use stable SHA-256-based seed derivation rather than `hash()`.

Given the same:

- frozen inputs;
- config;
- package lock;
- benchmark version;

all deterministic components should produce identical manifests, scores, candidate sets, metrics, hashes, and output ordering.

Sort only where sorting is part of the specification. Preserve stored dynamic-pool ordering in prompts.

Never assume temperature zero makes hosted inference deterministic. Record model/provider configuration instead.

---

## Wordle engine rules

The deterministic scorer is research-critical.

For a secret and guess:

1. mark exact-position matches first;
2. consume those matched secret letters;
3. count unmatched secret letters;
4. assign `PRESENT` only while an unmatched occurrence remains;
5. otherwise assign `ABSENT`.

Do not approximate repeated-letter behavior with simple membership checks.

Constraint consistency should preferably be defined behaviorally:

```python
candidate_is_consistent = all(
    score(candidate, old_guess) == old_feedback
    for old_guess, old_feedback in history
)
```

This avoids maintaining a separate, potentially inconsistent hand-written rule system for duplicate letters.

---

## Validation rules

For every generated candidate string, classify using the precedence in `DESIGN.md`:

1. `FORMAT_ERROR`
2. `LEXICON_ERROR`
3. `CONSTRAINT_ERROR`
4. `VALID`

Record all top-three guesses independently.

Only the top-ranked guess controls the game action.

Do not assign arbitrary numerical severity weights to error classes. Error rates are diagnostic metrics; game consequences are governed by the repair/forfeit protocol.

For `dynamic_256`, a five-letter English word outside the instance pool is still lexicon-invalid for that game.

---

## Prompt discipline

Prompt text is part of the benchmark and therefore versioned experimental material.

Prompt builders must be deterministic for a given state.

The instructional prose for `hist_unnamed` and `dynamic_256` must not contain, case-insensitively:

```text
wordle
green
yellow
gray
grey
nyt
new york times
hard mode
```

Do not filter or rewrite lexical payloads to satisfy this check. Candidate words, accepted guesses, and rejected proposals must remain verbatim and are tested separately from instructional prose.

Do not casually rewrite prompts while debugging model behavior. Prompt debugging occurs on development manifests only.

Once evaluation prompts are frozen:

- hash them/version them;
- do not edit them after observing evaluation results;
- if a correctness bug requires an edit, bump the prompt/benchmark version and rerun all affected comparisons.

Repair prompts may reveal the error class but must not reveal the exact violated clue or provide a valid replacement.

---

## Provider adapter rules

The benchmark core should target a small common interface, e.g.:

```python
class ModelAdapter(Protocol):
    async def predict(self, prompt: str) -> ModelResponse:
        ...
```

A provider adapter is responsible for:

- sending one stateless request;
- returning the raw response;
- extracting the requested top-three strings without semantically correcting them;
- reporting token usage where available;
- reporting latency;
- reporting the exact model identifier/configuration;
- retrying only transient infrastructure failures.

A provider adapter must not:

- maintain conversation IDs between benchmark turns;
- use `previous_response_id` or equivalent conversational carry-over;
- solve/validate Wordle itself;
- silently replace invalid model guesses;
- retry a semantic/model error as though it were an infrastructure failure.

Credentials come from environment variables or secret management. Never commit keys.

Exact provider model IDs and prices belong in configuration, not game logic.

---

## Retry semantics

Distinguish infrastructure retries from experimental repair attempts.

Infrastructure examples:

- HTTP timeout;
- connection reset;
- rate limit;
- provider 5xx.

These may be retried according to a bounded backoff policy and do **not** count as game repair attempts.

Experimental invalidity examples:

- six-letter word;
- nonexistent/disallowed word;
- contradiction of prior feedback.

These must be recorded as model behavior and handled using the single repair attempt defined by the experiment.

Never conflate the two.

---

## Logging and resumability

Do not rely on console output as experimental data.

Every proposal should be logged with enough information to reproduce downstream analysis, including:

- run/game/model/mode IDs;
- round;
- initial vs repair;
- raw top-three strings;
- validity/error category for each;
- information-gain values where applicable;
- candidate count before/after;
- accepted guess and feedback;
- usage and latency;
- prompt/config/model hashes/versions.

Every completed game should have exactly one game-summary record.

Runs must be resumable without duplicating completed model × condition × game combinations.

Prefer append-safe intermediate output and an explicit finalization/aggregation step.

Do not overwrite raw experiment results by default.

---

## Cost safety

No paid provider calls should occur during import, tests, manifest generation, or ordinary local development.

Provider integration tests requiring real API calls must be explicitly opt-in, e.g. via a CLI flag or pytest marker.

Support a run-level cost guard such as:

```bash
uv run python -m benchmark run ... --max-cost-usd 5
```

Capture provider-reported token usage when possible. Pricing is configuration data and should be easy to update immediately before a final run.

Never launch the full evaluation suite as part of an automated test.

---

## Testing expectations

Run deterministic tests frequently:

```bash
uv run pytest
```

Before considering Milestones 1–3 complete, tests must cover at least:

- standard scoring;
- all exact/all absent;
- repeated letters in secret and/or guess;
- constraint consistency against old and recent clues;
- candidate filtering;
- information gain on hand-enumerable toy sets;
- dynamic pool legality;
- prompt contamination checks;
- session isolation;
- one-repair semantics;
- failed-repair round forfeiture;
- manifest reproducibility;
- mock-provider complete games.

Tests should not call paid APIs by default.

When fixing a research-critical bug, add a regression test first or alongside the fix.

---

## Dependency policy

Keep dependencies minimal.

Likely runtime dependencies include only what is actually needed for:

- configuration;
- provider SDKs / HTTP clients;
- dataframes/Parquet;
- `wordfreq` dictionary construction;
- analysis/plotting.

Add dependencies using `uv add`, not by directly editing an environment outside the project.

Use dependency groups/dev dependencies for test and development tools.

Do not add a heavy dependency when a short deterministic standard-library implementation is clearer.

---

## CLI expectations

Expose one coherent CLI through:

```bash
uv run python -m benchmark ...
```

The exact command organization may evolve, but the MVP should support workflows equivalent to:

```bash
# Generate and freeze manifests.
uv run python -m benchmark generate-manifests --config configs/benchmark.yaml

# Run a development slice against the mock provider.
uv run python -m benchmark run \
  --config configs/benchmark.yaml \
  --models mock \
  --mode dynamic_256 \
  --split dev

# Run a configured model against one condition.
uv run python -m benchmark run \
  --config configs/benchmark.yaml \
  --models gpt-4o \
  --mode hist_named \
  --split dev

# Aggregate/analyze completed runs.
uv run python -m benchmark analyze --results results/<run-id>
```

Prefer explicit flags over hidden environment-driven behavior, except for credentials.

---

## Work style for Codex / coding agents

For nontrivial tasks:

1. read relevant project docs/code first;
2. state a short implementation plan;
3. implement the smallest coherent slice;
4. run relevant tests;
5. fix failures caused by the change;
6. summarize what changed and any unresolved risks.

Do not perform broad unrelated refactors during a focused task.

When code and documentation disagree, determine whether this is:

- a code bug;
- stale documentation;
- or an experimental-design conflict.

Do not choose silently when the answer would change experimental results.

Favor working, testable vertical slices over scaffolding large unused abstractions.

---

## Things not to implement in the MVP

Unless explicitly requested after the base benchmark works, do not add:

- chain-of-thought capture or grading;
- browsing/tools during gameplay;
- multi-agent systems;
- a web frontend;
- arbitrary composite benchmark scores;
- dozens of extra models;
- automated prompt optimization;
- provider-side conversational state;
- automated fine-tuning;
- feedback-label ablations;
- automatic fallback to top-2/top-3 guesses.

Qwen3 4B and fine-tuning are not part of the MVP.

---

## Definition of a good change

A good change should leave the repository in a state where:

- deterministic tests pass;
- experimental invariants remain intact;
- output is reproducible where it should be;
- new behavior is typed and tested;
- paid calls remain explicit;
- raw model behavior is preserved rather than cleaned up;
- configuration, not source-code edits, controls provider/model deployment details;
- another researcher could understand how the result was generated.
