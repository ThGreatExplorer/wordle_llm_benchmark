# Wordle LLM Benchmark: MVP Design Specification

**Status:** Frozen MVP v2 design for implementation
**Audience:** Codex / software engineer implementing the benchmark
**Primary language:** Python 3.11+
**Purpose:** Build a reproducible benchmark for multi-turn lexical constraint reasoning across six language models.

---

## 1. Project summary

Build a deterministic local Wordle-style game engine plus a stateless LLM evaluation harness. The system evaluates six models across three game conditions using frozen test manifests. Each model must receive the same instances within a condition. Every LLM turn is a fresh API/model call reconstructed from the public game state; no provider conversation state may persist between turns or games.

The benchmark studies whether models can:

1. maintain hard lexical/positional constraints over multiple turns;
2. choose strategically informative guesses;
3. rank good candidates correctly among their top three suggestions; and
4. repair invalid outputs after a single verifier rejection.

This project is an evaluation harness first. Fine-tuning is explicitly optional and out of scope for the MVP.

---

## 2. Research questions

### RQ1
How does multi-turn word-constraint reasoning vary across frontier, legacy, and open-weight language models?

### RQ2
How much does recognizing the task as Wordle improve performance?

### RQ3
Does changing Wordle from a fixed historical answer distribution to dynamically generated candidate spaces reduce frontier-model saturation?

---

## 3. Models

The frozen six-model comparison is:

### OpenAI generation track

1. GPT-4o
2. GPT-5
3. GPT-5.6

### Qwen3 parameter-scaling track

4. Qwen3 8B
5. Qwen3 14B
6. Qwen3 32B

Do not hard-code provider-specific model IDs into game logic. Put exact model identifiers, reasoning settings, endpoints, pricing, and credentials in configuration.

For the main benchmark, use direct/non-thinking or the lowest practical reasoning mode so that inference-time reasoning budgets are not intentionally varied across families. Record the exact inference configuration for every run.

All Qwen tracks MUST run through OpenRouter's OpenAI-compatible Chat Completions endpoint. Use the frozen OpenRouter model slugs `qwen/qwen3-8b`, `qwen/qwen3-14b`, and `qwen/qwen3-32b`. Qwen3 4B is not part of the benchmark because it is not available in the selected OpenRouter deployment. Disable reasoning/thinking through OpenRouter's normalized reasoning configuration and require routed providers to support every requested parameter, including structured outputs. Record the returned model and provider metadata available from each response.

---

## 4. Frozen experimental matrix

There are three conditions and 150 evaluation instances per condition per model.

| Condition | Task name exposed? | Secret universe | Legal guess universe | Instance count |
|---|---|---|---|---:|
| `hist_named` | Yes: Wordle | Original 2022 Wordle solution list | Original 2022 Wordle legal guesses | 150 |
| `hist_unnamed` | No | Same as `hist_named` | Same as `hist_named` | 150 |
| `dynamic_256` | No | Per-instance 256-word pool | Exactly the same per-instance 256 words | 150 |

Total games:

`6 models * 3 conditions * 150 instances = 2700 games`

A game has at most **6 decision rounds**.

### Pairing rules

- `hist_named` and `hist_unnamed` MUST use the exact same 150 secrets, in the same manifest order.
- Every model MUST receive those same 150 historical instances.
- `dynamic_256` MUST contain 150 frozen independently generated candidate pools/secrets.
- Every model MUST receive the exact same 150 dynamic instances, including identical candidate ordering.
- The dynamic instances are not semantically paired with historical instances; do not pretend that dynamic instance 42 is the same puzzle as historical instance 42.

---

## 5. Development data versus evaluation data

Create separate development manifests before the frozen evaluation manifests.

Recommended development set:

- 10 historical targets
- 10 dynamic-256 instances

Development instances may be used for:

- prompt debugging;
- API integration;
- parser debugging;
- engine correctness checks;
- cost estimation;
- concurrency tuning.

They MUST NOT be included in the final 150-instance evaluation manifests.

Once final evaluation manifests and prompt templates are frozen, do not modify them after inspecting evaluation results. If a bug forces a change, bump the benchmark/prompt version and rerun all affected models rather than mixing versions.

---

## 6. Data sources and frozen word lists

### 6.1 Historical Wordle data

Use frozen copies of the original pre-NYT/original-2022 Wordle source lists:

- 2,315 possible solution words;
- 10,657 additional accepted guesses;
- legal historical guess set = union of the two lists.

For the MVP, sample the 150 historical secrets uniformly without replacement from the 2,315 original solution list. This is a historical Wordle-lexicon baseline, not necessarily a sample restricted to already-published daily puzzles.

Store frozen normalized files such as:

```text
data/frozen/wordle_answers_2022.txt
data/frozen/wordle_extra_guesses_2022.txt
```

Normalize to lowercase ASCII. Validate that every entry is exactly five alphabetic ASCII letters.

Record SHA-256 hashes and provenance in `data/README.md`.

### 6.2 Dynamic dictionary

Build a separate dynamic master vocabulary from:

1. SCOWL level 60, American English; intersected with
2. the `wordfreq` small/common English vocabulary; then filtered to
3. lowercase ASCII alphabetic words of exactly length 5.

Remove the original 2,315 Wordle solution words from the resulting dynamic dictionary.

Do **not** remove the entire historical Wordle legal-guess list, because that risks disproportionately retaining obscure words.

The final dynamic dictionary must be generated once, frozen, hashed, and reused for every dynamic instance.

Suggested output:

```text
data/frozen/dynamic_master_5letter.txt
```

The repository should include a reproducible script such as:

```text
scripts/build_dynamic_dictionary.py
```

The script should accept an explicit SCOWL input path and use the installed `wordfreq` package. It should not silently change the dictionary during benchmark execution.

---

## 7. Manifest generation

Use one benchmark master seed. Generate manifests once, save the fully materialized instances, and never regenerate them during evaluation.

Suggested files:

```text
data/manifests/dev_historical.jsonl
data/manifests/dev_dynamic.jsonl
data/manifests/eval_historical.jsonl
data/manifests/eval_dynamic.jsonl
```

### 7.1 Historical manifest record

Example:

```json
{
  "benchmark_version": "mvp-v2",
  "game_id": "hist_0042",
  "secret": "crane"
}
```

The same `eval_historical.jsonl` drives both `hist_named` and `hist_unnamed`.

### 7.2 Dynamic manifest record

Example:

```json
{
  "benchmark_version": "mvp-v2",
  "game_id": "dynamic_0042",
  "pool_seed": 82910422,
  "secret_seed": 19328501,
  "pool": ["abide", "crane", "... exactly 256 entries ..."],
  "secret": "torch"
}
```

Derive independent pool and secret seeds from a master seed plus stable labels/game IDs. Do not rely on Python's built-in `hash()` because it is process-salted. Use a stable hash such as SHA-256 and convert part of the digest to an integer.

Example conceptual derivation:

```python
pool_seed = stable_seed(MASTER_SEED, "pool", game_id)
secret_seed = stable_seed(MASTER_SEED, "secret", game_id)
```

Generate:

```python
pool = pool_rng.sample(dynamic_dictionary, 256)
secret = secret_rng.choice(pool)
```

Once stored, the materialized `pool` and `secret` fields are authoritative. The benchmark runner reads them; it does not regenerate them.

Preserve the stored order of the 256 words in prompts so all models see the same ordering.

---

## 8. Deterministic Wordle engine

The LLM must never evaluate its own answers. All game behavior is implemented locally in Python.

### 8.1 Feedback labels

Use the same labels in all three conditions:

- `EXACT`: guessed letter matches the secret in this position.
- `PRESENT`: guessed letter occurs in the secret in another still-unmatched position.
- `ABSENT`: no unmatched occurrence of this letter remains in the secret.

The labels must be ordered left-to-right, one per guessed letter.

### 8.2 Duplicate-letter semantics

Implement standard Wordle duplicate handling using two passes:

1. mark and consume all exact-position matches;
2. count the remaining unmatched letters in the secret;
3. scan remaining guess positions and assign `PRESENT` only while an unmatched copy remains; otherwise assign `ABSENT`.

The engine function should conceptually be:

```python
score(secret: str, guess: str) -> tuple[Feedback, Feedback, Feedback, Feedback, Feedback]
```

This function must be heavily unit-tested, especially with repeated letters in the secret and/or guess.

---

## 9. Strict hard-mode constraint semantics

This benchmark is about constraint satisfaction. Every **accepted** played guess after prior feedback must be fully consistent with all previous feedback, not merely satisfy a subset of official UI hard-mode rules.

Given history:

```text
(g_1, r_1), ..., (g_k, r_k)
```

where `score(secret, g_i) = r_i`, a lexical candidate `x` is constraint-consistent iff:

```text
score(x, g_i) == r_i  for every previous i
```

This identity is the authoritative hard-mode validator. Do not manually reimplement a separate collection of green/yellow/count rules.

### Candidate-secret set

At round `t`, feasible secrets are:

```text
S_t = {s in S_0 : score(s, g_i) == r_i for every accepted prior guess i}
```

For historical modes:

- `S_0` = 2,315 Wordle answers;
- lexical guess universe = 2,315 answers + 10,657 extra legal guesses.

For dynamic mode:

- `S_0` = the current instance's 256-word pool;
- lexical guess universe = the same 256-word pool.

A historical legal guess may be a non-answer word, but it still must be fully consistent with all prior feedback to be accepted.

---

## 10. Prompt design

Use one canonical output contract and nearly identical rules across conditions. The purpose of `hist_named` versus `hist_unnamed` is to isolate recognition of the task name, not to change the underlying explanation.

All prompts should have an explicit version identifier in code, for example `prompt-v1`.

### 10.1 Common output instruction

Every prediction must request exactly three ranked guesses, best first.

Canonical semantic contract:

```json
{
  "guesses": ["crane", "slate", "trace"]
}
```

The schema may enforce:

- one object;
- one `guesses` field;
- exactly 3 strings.

Do **not** constrain the strings to five letters or to a word-list enum at the API schema layer. Those are benchmark behaviors to validate locally.

Do not ask for chain-of-thought or explanations. The benchmark output is the three ranked guesses only.

### 10.2 Named historical prompt

Use wording equivalent to the following and freeze the exact final text:

```text
You are playing Wordle under a strict hard-mode rule.

The secret is a five-letter English word.

After each accepted guess, you receive one label for each letter:
- EXACT: the letter is in the secret at this exact position.
- PRESENT: the letter occurs in the secret, but not at this position among the still-unmatched letters.
- ABSENT: no unmatched occurrence of this letter remains in the secret.

Every new guess must be a legal five-letter Wordle guess and must be fully consistent with all feedback from every previous accepted guess.

Return exactly three ranked next guesses, from best to worst, using the required JSON format. Do not include explanation.
```

Then append the full accepted public history and the current round number.

### 10.3 Unnamed historical prompt

This should differ from the named prompt only where necessary to remove explicit task recognition:

```text
You are playing a five-letter word deduction game under a strict consistency rule.

The secret is a five-letter English word.

After each accepted guess, you receive one label for each letter:
- EXACT: the letter is in the secret at this exact position.
- PRESENT: the letter occurs in the secret, but not at this position among the still-unmatched letters.
- ABSENT: no unmatched occurrence of this letter remains in the secret.

Every new guess must be a legal five-letter English guess for this game and must be fully consistent with all feedback from every previous accepted guess.

Return exactly three ranked next guesses, from best to worst, using the required JSON format. Do not include explanation.
```

The frozen instructional prose must not use the words `Wordle`, `green`, `yellow`, `gray`, `NYT`, or `hard mode`. Lexical payloads such as candidate lists, accepted guesses, and rejected proposals are preserved verbatim and are excluded from this contamination check.

### 10.4 Dynamic-256 prompt

Use the unnamed rules, then add:

```text
For this game, the secret was selected uniformly from exactly the 256 candidate words listed below.

Every guess must:
1. be one of these 256 words; and
2. be fully consistent with all feedback from every previous accepted guess.

Candidate words, in fixed order:
<256 WORDS>
```

The 256 words are included on **every** reconstructed turn, in the same fixed order for that instance.

---

## 11. Stateless session protocol

Do not run games as persistent provider conversations.

For every decision round, construct a brand-new request containing:

1. the frozen condition rules;
2. dynamic pool if applicable;
3. all accepted public guesses and feedback so far;
4. current round number;
5. the output instruction.

Do not pass provider conversation IDs, previous-response IDs, hidden model state, or previous assistant messages.

Only **accepted played guesses** and their deterministic feedback enter the next normal game-state prompt.

The prior round's second- and third-ranked suggestions are measurements only. They must not be shown back to the model on the next normal turn.

Every game starts from an entirely fresh state.

---

## 12. Decision-round and repair protocol

A game has at most six **decision rounds**.

### 12.1 Initial proposal

At the start of a round:

1. reconstruct the prompt from scratch;
2. request three ranked guesses;
3. validate the first-ranked guess as the proposed action;
4. independently validate all three guesses for diagnostics.

Only guess #1 is eligible to be played. Do not automatically promote guess #2 or #3 if guess #1 is invalid.

### 12.2 One repair attempt

If the first-ranked guess is invalid:

1. record the initial error;
2. make exactly one fresh repair request;
3. reconstruct all rules and game state again;
4. include the invalid first-ranked proposal and only its error class;
5. request three new ranked guesses;
6. validate repaired guess #1.

Example repair suffix:

```text
Your previous first-ranked proposal "xxxxx" was rejected with CONSTRAINT_ERROR: it is inconsistent with at least one previously established constraint.

Re-evaluate the complete game state and return exactly three new ranked guesses in the required format. Do not include explanation.
```

Do not reveal which exact clue was violated.

If repaired guess #1 is valid, play it.

If repaired guess #1 is still invalid, the decision round is forfeited and no guess is played/no new feedback is generated. Move to the next decision round with the same accepted game history.

A failed repair therefore consumes one of the six decision rounds.

### 12.3 Win and loss

- Win: an accepted played guess equals the secret within six decision rounds.
- Loss: the secret is not solved after decision round 6.

---

## 13. Validation and error taxonomy

Keep action-invalidating error classes mutually exclusive using a fixed precedence.

### Response-level error

`PROTOCOL_ERROR`

Use when the system cannot extract exactly three string suggestions from the response under the provider adapter's expected output contract.

### Guess-level validation precedence

For each extracted guess, validate in this order:

1. `FORMAT_ERROR`
   - not exactly five ASCII alphabetic letters after only minimal normalization such as trimming whitespace/lowercasing;
2. `LEXICON_ERROR`
   - format-valid but not in the condition's lexical guess universe;
3. `CONSTRAINT_ERROR`
   - format- and lexicon-valid but inconsistent with one or more prior accepted feedback constraints;
4. `VALID`.

For dynamic mode, add diagnostic subcode `OUTSIDE_DYNAMIC_POOL` to `LEXICON_ERROR`.

Do not assign arbitrary numeric severity weights to these errors.

Their natural consequences are sufficient:

- invalid first proposal triggers repair;
- invalid repair forfeits a decision round;
- repeated failures reduce solve rate and increase round score.

### Non-invalidating diagnostics

The following may be logged but must not reject a guess:

- `REPEAT_ACCEPTED_GUESS`: proposal repeats an earlier accepted guess but is otherwise legal/consistent;
- `DUPLICATE_TOP3`: two or more of the three suggestions are identical.

---

## 14. Provider abstraction

Game logic must depend on a minimal adapter interface, not individual SDKs.

Suggested data types:

```python
@dataclass
class ModelResponse:
    guesses: list[str] | None
    raw_text: str
    input_tokens: int | None
    output_tokens: int | None
    reasoning_tokens: int | None
    latency_ms: float
    provider_request_id: str | None
    model_returned: str | None
    protocol_error: str | None

class ModelAdapter(Protocol):
    async def predict(self, prompt: str) -> ModelResponse:
        ...
```

Implement at least:

```text
providers/openai_responses.py
providers/openai_compatible.py
providers/mock.py
```

`openai_compatible.py` targets OpenRouter for the Qwen tracks. Keep the base URL and model slug configurable, but do not use locally hosted Qwen models in the primary benchmark.

### Provider responsibilities

A provider adapter may:

- send a prompt;
- request the minimal JSON object contract if supported;
- parse the response;
- capture usage and latency;
- retry transient network/rate-limit failures according to infrastructure policy.

A provider adapter may NOT:

- validate Wordle legality;
- fix a model's invalid word;
- choose a fallback suggestion;
- maintain game conversation state;
- expose chain-of-thought.

Infrastructure retries for failed HTTP requests are separate from the benchmark's one semantic repair attempt. Network retries must not count as model repair attempts.

---

## 15. Model configuration

Create a config file such as:

```text
configs/models.yaml
```

Conceptual structure:

```yaml
models:
  gpt4o:
    provider: openai
    model: <pinned-model-id>
    temperature: 0
    reasoning_effort: null
    input_price_per_million: <configurable>
    output_price_per_million: <configurable>

  gpt5:
    provider: openai
    model: <pinned-model-id>
    temperature: 0
    reasoning_effort: <lowest/direct mode supported>

  gpt56:
    provider: openai
    model: <pinned-model-id>
    temperature: 0
    reasoning_effort: <none/direct mode if supported>

  qwen3_8b:
    provider: openai_compatible
    base_url: https://openrouter.ai/api/v1
    model: qwen/qwen3-8b
    temperature: 0
    thinking: false
```

Repeat for Qwen3 14B and 32B using their exact OpenRouter slugs.

Do not assume deterministic inference merely because temperature is zero. Record configuration and treat the 150 frozen instances as the experimental sample. If a provider exposes a request seed, it may be recorded/used, but the benchmark must not rely on it for correctness.

---

## 16. Main runner

The runner should operate at the game level with bounded concurrency. Rounds within one game are sequential; different games may run concurrently.

Conceptual flow:

```python
async def run_game(model, condition, instance):
    state = fresh_state(instance)

    for decision_round in range(1, 7):
        prompt = build_normal_prompt(condition, state, decision_round)
        initial = await model.predict(prompt)
        initial_eval = evaluate_top3(initial, state, condition)
        log_proposal(...)

        if initial_eval.top1_valid:
            chosen = initial_eval.top1
        else:
            repair_prompt = build_repair_prompt(
                condition,
                state,
                decision_round,
                initial_eval.top1_raw,
                initial_eval.top1_error,
            )
            repair = await model.predict(repair_prompt)
            repair_eval = evaluate_top3(repair, state, condition)
            log_proposal(...)

            if not repair_eval.top1_valid:
                log_forfeit(...)
                continue

            chosen = repair_eval.top1

        feedback = score(instance.secret, chosen)
        state.accept(chosen, feedback)

        if chosen == instance.secret:
            return solved_summary(...)

    return failed_summary(...)
```

### Concurrency

Support a configurable concurrency limit, for example:

```text
--concurrency 8
```

Do not parallelize rounds within a single game.

Support resumability: if a run is interrupted, already completed game/model/condition keys should not be recomputed unless explicitly requested.

---

## 17. Information-gain oracle

Information gain is computed deterministically from the current feasible secret set.

Let current feasible secrets be `S_t` and let `g` be a valid hard-mode guess. Partition `S_t` by the feedback pattern that would result from guessing `g`.

Under the benchmark's uniform prior over `S_t`:

```text
H(S_t) = log2(|S_t|)
```

and expected posterior entropy is:

```text
sum_r p(r) * log2(|S_{t,r}|)
```

where `S_{t,r}` is the subset yielding feedback `r`.

Define:

```text
IG(g) = H(S_t) - expected_posterior_entropy
```

Equivalent implementations based on feedback-pattern entropy are acceptable if numerically identical.

### Oracle legal-guess set

When finding `IG*`, only compare against guesses that are currently valid under the benchmark's strict hard-mode rule.

- Historical: all original legal Wordle guesses that are constraint-consistent.
- Dynamic: all words in the current 256 pool that are constraint-consistent.

Define:

```text
IG_star = max_g IG(g)
```

Cache aggressively. A precomputed feedback-pattern matrix for the historical answer/guess lexicons is acceptable and recommended if needed for performance.

---

## 18. Metrics

### 18.1 Primary metrics

#### Solve@6

```text
number of games solved within six decision rounds / total games
```

#### Mean decision-round score

For game `G`:

```text
score(G) = decision round of solution, if solved
score(G) = 7, if unsolved
```

Report the mean across all 150 games. This is the primary efficiency metric because failures remain in the denominator.

Also report mean accepted guesses among wins as a descriptive secondary statistic, but do not use it as the main efficiency measure.

### 18.2 Constraint fidelity

#### Initial Valid@1

Fraction of **initial** first-ranked proposals that are `VALID`.

Repairs are excluded from this metric because it measures autonomous constraint maintenance before verifier intervention.

#### Initial Valid@3

Across initial top-three outputs, fraction of suggestions that are individually `VALID`.

This measures whether the model's broader proposed candidate set respects the state, even if its top-ranked action happens to be valid.

### 18.3 Constraint-memory depth

For every lexicon-valid suggestion, identify all prior accepted clues it contradicts:

```text
score(candidate, prior_guess_i) != prior_feedback_i
```

For a proposal made on round `t`, define clue age:

```text
age = t - i
```

Store all violated ages, plus minimum and maximum violated age.

For analysis, compute violation probability by clue age. Use an exposure-aware denominator: a clue of age `k` is only included when the current state actually contains a clue `k` rounds old.

This metric answers whether constraint failures increase as information becomes older in the interaction history.

### 18.4 Strategic quality from top three

Compute information gain for each valid suggested guess.

#### Top-1 normalized information efficiency

When `IG_star > 0`:

```text
IG_efficiency = IG(g1) / IG_star
```

If top-1 is invalid, store the strategic value as missing for the valid-guess strategic analysis and separately account for the constraint failure. Do not invent an information score for an impossible action.

#### Search regret

Among valid suggestions in the top three:

```text
search_regret = IG_star - max(IG(valid top3 suggestions))
```

If none of the top three are valid, this value is missing and the state is already captured by constraint-fidelity metrics.

This measures failure to generate a strategically strong candidate anywhere in the top three.

#### Ranking regret

If top-1 is valid and at least one top-three suggestion is valid:

```text
ranking_regret = max(IG(valid top3 suggestions)) - IG(g1)
```

This measures whether the model generated a better option but ranked it below its chosen action.

#### Total top-1 regret

When top-1 is valid:

```text
total_regret = IG_star - IG(g1)
```

For valid top-1 states:

```text
total_regret = search_regret + ranking_regret
```

assuming the same validity handling and definitions above.

### 18.5 Repair capability

#### RepairSuccess

```text
P(repaired top1 is valid | initial top1 was invalid)
```

Report overall and stratified by initial error class:

- protocol;
- format;
- lexicon;
- constraint.

#### ForfeitRate

```text
number of failed repairs / number of decision rounds
```

or additionally conditional on repair attempts:

```text
P(repair also invalid | repair attempted)
```

Label denominators explicitly.

### 18.6 Diagnostic-only metrics

These may be logged and shown if interesting, but are not headline benchmark metrics:

- output error frequency by class;
- `DUPLICATE_TOP3` rate;
- repeated accepted-guess rate;
- token usage;
- latency;
- cost;
- `Secret@3` only for late-game states with `|S_t| <= 10`.

Do not create a single arbitrary weighted "failure score" combining different error types.

---

## 19. Analysis plan by research question

### RQ1: model capability differences

For each model and condition, report at minimum:

- Solve@6;
- mean decision-round score;
- Initial Valid@1;
- Initial Valid@3;
- normalized IG efficiency;
- search regret;
- ranking regret;
- repair success;
- forfeit rate;
- constraint-violation curve by clue age.

For Qwen3 specifically, plot metrics against parameter scale (8B, 14B, 32B).

For OpenAI, describe GPT-4o -> GPT-5 -> GPT-5.6 as a model-generation comparison, not a parameter-scaling curve.

### RQ2: task recognition effect

This is the clean paired contrast:

```text
hist_named versus hist_unnamed
```

The secret is identical for each paired game ID.

For each model calculate paired deltas in:

- Solve@6;
- round score;
- Initial Valid@1;
- IG efficiency;
- repair behavior if sample size permits.

Use paired bootstrap confidence intervals over historical game IDs. McNemar's test for paired solve outcomes may be included, but effect sizes and confidence intervals are more important than collecting many p-values.

### RQ3: dynamic candidate-space generalization

Primary comparison:

```text
hist_unnamed versus dynamic_256
```

Do not use `hist_named` as the main comparison because that would mix the RQ2 recognition effect into RQ3.

This is not a perfectly isolated causal ablation: dynamic mode changes vocabulary construction, candidate-pool presentation, and legal-guess universe. Treat it as an out-of-distribution/generalization validation condition.

Compare saturation/degradation using:

- Solve@6;
- round score;
- Valid@1;
- IG efficiency;
- constraint-memory behavior.

Do not use paired statistical tests between historical and dynamic instances because their secrets/pools are different. Use bootstrap intervals over each condition and report changes with appropriate uncertainty.

---

## 20. Statistical defaults

Use 150 evaluation games per condition/model.

Recommended uncertainty method:

- 10,000 bootstrap resamples over game IDs;
- 95% confidence intervals.

Within a condition, model-to-model comparisons may be paired by game ID because all models see the same instances.

For `hist_named` versus `hist_unnamed`, pair by the historical game ID.

For historical versus dynamic, use independent condition resampling rather than artificial pairing.

The benchmark is intended to identify medium/large capability gaps, not distinguish tiny differences near saturation.

---

## 21. Logging/data model

Store one row per model proposal (initial or repair) plus one row per completed game summary.

Use Parquet as the main analysis format and JSONL optionally for raw/auditable logs.

### 21.1 Proposal log fields

At minimum:

```text
run_id
benchmark_version
prompt_version
game_id
condition
model_key
provider
requested_model_id
returned_model_id
decision_round
proposal_type              # initial | repair

raw_response
guess_1
guess_2
guess_3

valid_1
valid_2
valid_3
error_1
error_2
error_3
error_subcode_1
error_subcode_2
error_subcode_3

violated_constraint_ages_1
violated_constraint_ages_2
violated_constraint_ages_3

candidate_count_before
ig_1
ig_2
ig_3
ig_star
ig_efficiency_top1
search_regret
ranking_regret
total_regret

accepted_guess
feedback
candidate_count_after

input_tokens
output_tokens
reasoning_tokens
latency_ms
estimated_cost_usd
provider_request_id

prompt_hash
model_config_hash
manifest_hash
timestamp_utc
```

Use nulls where a value does not make sense rather than fake zeros.

### 21.2 Game summary fields

At minimum:

```text
run_id
game_id
condition
model_key
solved
solve_round
round_score              # solve_round or 7
accepted_guess_count
initial_invalid_count
repair_attempt_count
repair_success_count
forfeit_count
protocol_error_count
format_error_count
lexicon_error_count
constraint_error_count
input_tokens_total
output_tokens_total
reasoning_tokens_total
estimated_cost_usd_total
latency_ms_total
```

---

## 22. Cost accounting and budget guardrails

Do not hard-code current public prices into analysis code. Put per-million token prices in model configuration so they can be updated immediately before the final run.

For every response, capture provider-reported input/output/reasoning token usage when available and compute estimated cost from the run's frozen pricing config.

Implement:

- per-game cumulative cost;
- per-model cumulative cost;
- total run cost;
- a configurable budget stop such as `--max-cost-usd`;
- a development/dry-run mode.

A development run on the 10+10 dev instances should be used to estimate actual calls/game and tokens/call before launching the 150-instance evaluation.

---

## 23. CLI requirements

The MVP should expose simple commands. Exact library is flexible (`argparse`, `typer`, etc.).

Suggested commands:

```bash
# Validate frozen word lists and manifests
python -m benchmark validate-data

# Generate development/evaluation manifests once
python -m benchmark generate-manifests --config configs/benchmark.yaml

# Run one model on development data
python -m benchmark run \
  --model gpt4o \
  --condition hist_unnamed \
  --split dev

# Run one model on evaluation data
python -m benchmark run \
  --model qwen3_8b \
  --condition dynamic_256 \
  --split eval \
  --concurrency 8

# Run the full matrix
python -m benchmark run-matrix \
  --split eval \
  --concurrency 8 \
  --resume

# Aggregate metrics
python -m benchmark analyze --run-id <RUN>
```

Implement `--resume` safely using a unique key such as:

```text
(run_id, model_key, condition, game_id)
```

A resumed run must not duplicate completed games.

---

## 24. Suggested repository structure

```text
wordle-llm-benchmark/
├── README.md
├── pyproject.toml
├── .env.example
├── AGENTS.md
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
│   ├── cli.py
│   ├── types.py
│   │
│   ├── engine/
│   │   ├── feedback.py
│   │   ├── state.py
│   │   ├── validator.py
│   │   └── information.py
│   │
│   ├── prompts/
│   │   ├── common.py
│   │   ├── named.py
│   │   ├── unnamed.py
│   │   └── dynamic.py
│   │
│   ├── providers/
│   │   ├── base.py
│   │   ├── mock.py
│   │   ├── openai_responses.py
│   │   └── openai_compatible.py
│   │
│   ├── experiment/
│   │   ├── runner.py
│   │   ├── manifests.py
│   │   ├── logging.py
│   │   └── pricing.py
│   │
│   └── analysis/
│       ├── metrics.py
│       ├── bootstrap.py
│       └── reports.py
│
├── scripts/
│   └── build_dynamic_dictionary.py
│
├── tests/
│   ├── test_feedback.py
│   ├── test_duplicates.py
│   ├── test_validator.py
│   ├── test_candidate_filtering.py
│   ├── test_information.py
│   ├── test_prompts.py
│   ├── test_repair_protocol.py
│   └── test_manifest_reproducibility.py
│
└── results/
    └── .gitkeep
```

---

## 25. Tests and acceptance criteria

Codex should not consider the MVP complete until the deterministic core is well tested.

### 25.1 Engine tests

Must verify:

- all-exact case;
- all-absent case;
- mixed exact/present/absent;
- duplicate letter in guess but only one copy in secret;
- duplicate letter in secret;
- multiple exact copies plus remaining present copies;
- known tricky repeated-letter cases.

### 25.2 Constraint-validator tests

Must verify:

- a true remaining secret is always constraint-consistent;
- candidates reproducing all historical feedback are valid;
- a candidate contradicting one old clue is invalid even if it satisfies newer clues;
- historical non-answer legal guesses can be valid guesses if fully consistent;
- dynamic guesses outside the 256 pool are lexicon-invalid;
- repeated prior guesses are not automatically invalid if consistent.

### 25.3 Information-gain tests

For tiny hand-built candidate sets, verify information gain against manually enumerable partitions.

Verify:

- `IG >= 0` up to floating-point tolerance;
- `IG <= log2(|S|)`;
- `IG_star` equals the maximum over the valid legal-guess set;
- a guess that produces the same feedback for every remaining secret has zero information gain.

### 25.4 Prompt tests

Automatically assert that the instructional prose for `hist_unnamed` and `dynamic_256` contains none of these banned strings case-insensitively:

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

Do not apply this assertion to lexical payloads. Assert separately that candidate lists, accepted guesses, and rejected proposals are reproduced verbatim.

Assert that named/unnamed historical prompts otherwise share the same feedback semantics and output contract.

### 25.5 Session-isolation tests

With the mock provider, verify:

- each normal round prompt contains all accepted public history;
- top-2/top-3 suggestions from prior turns are absent from the next normal prompt;
- repair prompts contain the relevant rejected top-1 and error class;
- repair prompts do not expose the exact violated clue;
- games do not share state;
- provider adapters receive no conversation ID/previous-response state from the benchmark core.

### 25.6 Manifest tests

Verify:

- exactly 150 eval historical records;
- exactly 150 eval dynamic records;
- no duplicate historical secrets;
- every dynamic pool has exactly 256 unique words;
- every dynamic secret is in its own pool;
- all dynamic words belong to the frozen dynamic master list;
- historical dev/eval instances are disjoint;
- dynamic dev/eval game IDs and seeds are disjoint;
- frozen manifest hashes match configuration/README metadata.

### 25.7 End-to-end mock test

Create a deterministic mock model with scripted valid/invalid behavior and run complete games to verify:

- successful solve;
- initial invalid -> successful repair;
- initial invalid -> failed repair -> forfeited round;
- six-round loss;
- correct logs and summaries for every case.

---

## 26. Reproducibility metadata

Every run should save a metadata file containing at least:

```text
run_id
started_at_utc
git_commit
benchmark_version
prompt_version
manifest hashes
word-list hashes
models.yaml hash
benchmark.yaml hash
Python version
package lock hash if available
host/platform metadata
provider/model identifiers
pricing config used
```

For OpenRouter Qwen runs, additionally record the requested model slug, returned model identifier, routing/provider metadata when available, pricing configuration, and reasoning mode.

---

## 27. MVP implementation order

Implement in this order so external API cost is incurred only after deterministic correctness is established.

### Milestone 1: deterministic core

- feedback engine;
- game state;
- strict constraint validation;
- candidate-set filtering;
- information gain;
- unit tests.

### Milestone 2: frozen data pipeline

- historical word-list validation;
- dynamic dictionary builder;
- stable seed utility;
- dev/eval manifest generation;
- manifest/hash tests.

### Milestone 3: prompts and mock harness

- named/unnamed/dynamic prompt builders;
- normal/repair protocol;
- top-three validation;
- proposal/game logging;
- mock model end-to-end tests.

### Milestone 4: provider integration

- official OpenAI Responses adapter;
- OpenRouter adapter through its OpenAI-compatible endpoint for Qwen;
- token/latency/cost capture;
- transient infrastructure retries;
- concurrency and resume.

### Milestone 5: analysis MVP

- aggregate primary/secondary metrics;
- bootstrap confidence intervals;
- export CSV/Parquet summary tables;
- basic plots for Solve@6, round score, Valid@1, IG efficiency, repair success, and constraint age.

Do not implement fine-tuning before these milestones work.

---

## 28. Explicit non-goals for MVP

Do NOT add these unless the core benchmark is complete:

- chain-of-thought collection or grading;
- agent tools/search/browsing during games;
- multi-agent play;
- alternative feedback-label ablations;
- prompt optimization after evaluation begins;
- arbitrary weighted composite benchmark score;
- automated fine-tuning;
- a web frontend;
- exhaustive testing of dozens of models;
- provider-side persistent conversations;
- automatic promotion of second/third guess when top-1 is invalid.

---

## 29. Frozen Qwen deployment decision

The primary benchmark uses OpenRouter exclusively for Qwen3 8B, 14B, and 32B. Do not substitute local serving, another aggregator, a newer Qwen generation, or Qwen3 4B without creating a new benchmark version and rerunning all affected comparisons. Fine-tuning remains outside the MVP.

---

## 30. Definition of MVP done

The MVP is complete when all of the following are true:

1. deterministic engine tests pass, including duplicate-letter cases;
2. dev and evaluation manifests can be generated and frozen reproducibly;
3. all three prompts satisfy contamination/naming checks;
4. a mock provider can run the entire game/repair protocol end to end;
5. OpenAI and OpenAI-compatible provider adapters can execute stateless calls;
6. one development game can be run successfully for an OpenAI model;
7. one development game can be run successfully against each configured OpenRouter Qwen track;
8. results are resumable and logged without duplicate completed games;
9. the analysis command computes primary metrics plus the agreed behavioral metrics;
10. no evaluation run depends on persistent LLM session state;
11. all run artifacts include prompt/config/manifest hashes.

---

## 31. First instruction to Codex

When beginning implementation, treat this document as the canonical experiment specification.

Before writing provider code, inspect the repository and create a short implementation plan. Then implement Milestones 1-3 first and run the deterministic test suite. Do not spend API money until the deterministic core, manifests, prompt checks, mock provider, and repair protocol pass locally.

Where provider SDK details or exact model identifiers have changed since this document was written, update only the provider/config layer using current official documentation. Do not silently change the experimental conditions, prompts, validation semantics, metrics, game count, or frozen data protocol.
