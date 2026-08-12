# Wordle LLM Benchmark: MVP Design Specification

**Status:** Frozen MVP v4 design for implementation
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

The mode dimension separates two related research questions. NORMAL asks whether
the model can solve the game and choose informative legal actions while measuring
constraint adherence as a diagnostic. It permits recovery through new feedback
after a constraint mistake. STRICT asks whether the model can solve while
maintaining exact cumulative constraints, producing only admissible actions, and
repairing verifier-rejected proposals. Both use identical prompts, instances,
scoring, and constraint diagnostics; the mode is evaluator policy and is never
revealed as strategic assistance.

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

All Qwen tracks MUST run through the dedicated stateless Hugging Face Inference Providers adapter using its OpenAI-compatible Chat Completions endpoint. Use the frozen model IDs `Qwen/Qwen3-8B:nscale`, `Qwen/Qwen3-14B:nscale`, and `Qwen/Qwen3-32B:nscale`, explicitly pinning Nscale for all sizes. Require strict structured output, disable reasoning with effort `none`, and record the exact requested and returned model metadata for every response.

---

## 4. Frozen experimental matrix

Condition and constraint-enforcement mode are separate dimensions. There are three
conditions and 150 frozen evaluation instances per condition per model.

| Condition | Task name exposed? | Secret universe | Legal guess universe | Instance count |
|---|---|---|---|---:|
| `hist_named` | Yes: Wordle | Original 2022 Wordle solution list | Original 2022 Wordle legal guesses | 150 |
| `hist_unnamed` | No | Same as `hist_named` | Same as `hist_named` | 150 |
| `dynamic_256` | No | Per-instance 256-word pool | Exactly the same per-instance 256 words | 150 |

The primary NORMAL experiment contains:

`6 models * 3 conditions * 150 instances = 2700 games`

The harness also supports STRICT mode over the same instances. STRICT is an
additional constraint-enforced evaluation and is not automatically part of the
2,700-game primary matrix. A later study may intentionally run both modes over
the full matrix.

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
  "benchmark_version": "mvp-v4",
  "game_id": "hist_0042",
  "secret": "crane"
}
```

The same `eval_historical.jsonl` drives both `hist_named` and `hist_unnamed`.

### 7.2 Dynamic manifest record

Example:

```json
{
  "benchmark_version": "mvp-v4",
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

## 9. Constraint consistency and execution modes

The benchmark supports two execution modes while using one shared deterministic
constraint checker.

- `normal`: every structurally and lexically legal top-1 is played. Constraint
  inconsistency is recorded but does not trigger repair or suppress feedback.
- `strict`: cumulative constraint consistency is enforced before play. An
  inconsistent top-1 triggers the one-repair protocol; a failed repair forfeits
  the decision round.

NORMAL is the primary general Wordle-solving evaluation. STRICT is an additional,
scientifically meaningful constraint-enforced evaluation; it is not deprecated.

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

A historical legal guess may be a non-answer word. In NORMAL it may be played even
when inconsistent; in STRICT it must be fully consistent to be played.

Internally, action validity and constraint consistency are independent. Action
validity requires five ASCII alphabetic letters and membership in the applicable
legal-guess universe. Every action-valid suggestion is separately replayed against
all prior played rows to compute constraint consistency and violated clue ages.

---

## 10. Prompt design

Use one canonical output contract and nearly identical rules across conditions. The purpose of `hist_named` versus `hist_unnamed` is to isolate recognition of the task name, not to change the underlying explanation.

The frozen prompt version is `prompt-v4`. Development runs with prompt-v2 showed that models frequently interpreted "fully consistent" differently from the benchmark's deterministic validator. Prompt-v3 therefore defined strict consistency operationally without changing the underlying validity rule or providing strategy assistance. Prompt-v4 keeps that specification unchanged and adds one compact symbolic consistency example as the final prompt ablation.

### 10.1 Common output instruction

Every prediction requests exactly three ranked guess strings, best first. The API schema may enforce:

- one object;
- one `guesses` field;
- exactly 3 strings.

Do **not** constrain the strings to five letters or to a word-list enum at the API schema layer. Those are benchmark behaviors to validate locally.

Do not ask for chain-of-thought or explanations. The benchmark output is the three ranked guesses only.

### 10.2 Named historical prompt

The named prompt uses this frozen instructional prose:

```text
You are playing Wordle under a strict consistency rule.

Your goal is to identify the secret five-letter English word within at most six decision rounds.

After each accepted guess, you receive exactly one feedback label for each letter:
- EXACT: the letter matches the secret at this exact position.
- PRESENT: the letter occurs in the secret, but not at this position among the still-unmatched letters.
- ABSENT: no unmatched occurrence of this letter remains in the secret.

Duplicate letters are evaluated as follows:
1. Assign all EXACT matches first.
2. For the remaining positions, assign PRESENT only while an unmatched occurrence of that letter remains in the secret.
3. Otherwise assign ABSENT.

STRICT CONSISTENCY RULE

Every one of the three guesses you return must be a legal five-letter Wordle guess and must independently satisfy every previous accepted feedback row.

To check whether a proposed word is consistent, temporarily treat that proposed word as if it were the secret. Re-evaluate each previous accepted guess against that proposed word using the feedback rules above.

For every previous accepted row, the five feedback labels produced in this check must exactly match the five recorded feedback labels for that row.

If even one label differs for any previous row, the proposed word is invalid.

You must check every previous accepted row, not only the most recent one.

CONSISTENCY EXAMPLE

Suppose a previous accepted row is:

Guess: ABCDE
Feedback: EXACT ABSENT PRESENT ABSENT ABSENT

Then any later valid proposal must:
- have A in position 1;
- not contain B, D, or E;
- contain C somewhere other than position 3;
- also satisfy every other previous feedback row.

A proposal that violates even one of these requirements is invalid.

The letter strings in this example illustrate consistency logic only and are not legal guesses for the game.

Never propose an already accepted guess again unless its recorded feedback was EXACT EXACT EXACT EXACT EXACT. Repeating a previously accepted unsolved guess cannot satisfy the strict consistency rule.

Only your first-ranked guess will actually be played. The second and third guesses are alternate recommendations, but they must also be valid under all of the same rules.

Before answering, silently verify each of your three proposed guesses against every previous accepted feedback row.

Return exactly one JSON object with exactly one field named "guesses". Its value must be an array of exactly three guess strings ranked from best to worst.

Do not include explanations, reasoning, or any other fields.
```

This specifies validity only. It provides no strategy, opening-word, information-gain, feasible-count, or remaining-candidate assistance.

### 10.3 Unnamed historical prompt

The unnamed prompt is identical in rule clarity and output contract, with only these task-identifying phrases changed:

- `You are solving a five-letter word deduction game under a strict consistency rule.`
- `Every one of the three guesses you return must be a legal five-letter English guess for this game and must independently satisfy every previous accepted feedback row.`

The frozen instructional prose must not use the words `Wordle`, `green`, `yellow`, `gray`, `NYT`, or `hard mode`. Lexical payloads such as candidate lists, accepted guesses, and rejected proposals are preserved verbatim and are excluded from this contamination check.

### 10.4 Dynamic-256 prompt

Use the exact unnamed rules, then add:

```text
CANDIDATE SET

For this game, the secret was selected uniformly from exactly the 256 candidate words listed below.

These 256 words are also the complete legal guess set for this game.

Every one of the three guesses you return must:
1. appear exactly in the candidate list below; and
2. satisfy the strict consistency rule for every previous accepted feedback row.

A word that satisfies the feedback constraints but is not in the candidate list is invalid.

Candidate words, in fixed order:
<256 WORDS>
```

The 256 words are included on **every** reconstructed turn, in the same fixed order for that instance.

### 10.5 Public history and repair formatting

Normal prompts contain only accepted public history, formatted as numbered rows with separate `Guess:` and `Feedback:` lines, followed by `Current decision round: N of 6`. Empty history is shown as `(none)`. They never contain the secret, feasible-set information, earlier rejected guesses, or prior alternate suggestions.

Repair prompts reconstruct the complete current prompt and append only the immediately preceding rejected top-1 plus its error class and semantic meaning. `CONSTRAINT_ERROR` explains the operational consistency failure but does not identify the violated row. Historical and dynamic `LEXICON_ERROR` distinguish illegal historical guesses from words outside the 256-word list. `FORMAT_ERROR` states the five-ASCII-letter requirement. `PROTOCOL_ERROR` describes the malformed response structure without inventing a rejected guess. No repair identifies an exact violated clue or supplies a replacement.

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

Repair triggers are mode-dependent. In NORMAL, repair occurs only for a response
protocol error or an action-invalid top-1 (`FORMAT_ERROR`, `LEXICON_ERROR`, or
dynamic `OUTSIDE_DYNAMIC_POOL`). An action-valid constraint violation is played
immediately. In STRICT, those same errors plus constraint inconsistency
(`CONSTRAINT_ERROR` at the execution gate) trigger repair.

When repair is triggered:

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

If repaired guess #1 satisfies the selected mode's play gate, play it. Thus NORMAL
requires action validity; STRICT requires action validity and consistency.

If repaired guess #1 still fails the selected mode's gate, the decision round is
forfeited and no guess is played/no new feedback is generated. Move to the next
decision round with the same played game history.

A failed repair therefore consumes one of the six decision rounds.

### 12.3 Win and loss

- Win: an accepted played guess equals the secret within six decision rounds.
- Loss: the secret is not solved after decision round 6.

---

## 13. Validation and error taxonomy

Validation produces two independent values:

```text
action_status = VALID | FORMAT_ERROR | LEXICON_ERROR
constraint_consistent = true | false | null
```

`constraint_consistent` is null for action-invalid strings and boolean for every
action-valid guess. `violated_constraint_ages` and repeat/duplicate diagnostics are
recorded independently.

### Response-level error

`PROTOCOL_ERROR`

Use when the system cannot extract exactly three string suggestions from the response under the provider adapter's expected output contract.

### Guess-level validation precedence

For each extracted guess, validate in this order:

1. `FORMAT_ERROR`
   - not exactly five ASCII alphabetic letters after only minimal normalization such as trimming whitespace/lowercasing;
2. `LEXICON_ERROR`
   - format-valid but not in the condition's lexical guess universe;
3. `VALID`, followed by deterministic constraint replay.

Constraint inconsistency exists as a diagnostic in both modes. In STRICT it is
also surfaced as `CONSTRAINT_ERROR` to the repair prompt and blocks play. In NORMAL
it is logged as `constraint_consistent=false`/constraint violation and does not
make the action invalid.

For dynamic mode, add diagnostic subcode `OUTSIDE_DYNAMIC_POOL` to `LEXICON_ERROR`.

Do not assign arbitrary numeric severity weights to these errors.

Their natural consequences are sufficient:

- an action-invalid first proposal triggers repair in both modes;
- constraint inconsistency additionally triggers repair in STRICT;
- a repair that still fails the selected mode's gate forfeits a decision round;
- repeated failures reduce solve rate and increase round score.

### Non-invalidating diagnostics

The following may be logged but must not reject a guess:

- `REPEAT_ACCEPTED_GUESS`: proposal repeats an earlier played guess;
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
    provider_returned: str | None
    provider_metadata: dict | None
    protocol_error: str | None

class ModelAdapter(Protocol):
    async def predict(self, prompt: str) -> ModelResponse:
        ...
```

Implement at least:

```text
providers/openai_responses.py
providers/openai_compatible.py
providers/huggingface_nscale.py
providers/mock.py
```

`huggingface_nscale.py` is the dedicated Qwen adapter. Its exact provider-suffixed model and base URL remain explicit configuration, while every request is stateless. `openai_compatible.py` is only the shared transport implementation; do not use it directly for primary Qwen runs.

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
    provider: huggingface_nscale
    base_url: https://router.huggingface.co/v1
    model: Qwen/Qwen3-8B:nscale
    inference_provider: nscale
    reasoning_effort: none
    temperature: 0
    input_price_per_million: null
    output_price_per_million: null
```

Repeat for Qwen3 14B and 32B using their exact Hugging Face model IDs with the `:nscale` suffix.

Do not assume deterministic inference merely because temperature is zero. Record configuration and treat the 150 frozen instances as the experimental sample. If a provider exposes a request seed, it may be recorded/used, but the benchmark must not rely on it for correctness.

---

## 16. Main runner

The runner should operate at the game level with bounded concurrency. Rounds within one game are sequential; different games may run concurrently.

Conceptual flow:

```python
async def run_game(model, condition, instance, game_mode):
    state = fresh_state(instance)

    for decision_round in range(1, 7):
        prompt = build_normal_prompt(condition, state, decision_round)
        initial = await model.predict(prompt)
        initial_eval = evaluate_top3(initial, state, condition)
        log_proposal(...)

        if initial_eval.top1_action_valid and (
            game_mode == NORMAL or initial_eval.top1_constraint_consistent
        ):
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

            if not repair_eval.top1_action_valid or (
                game_mode == STRICT and not repair_eval.top1_constraint_consistent
            ):
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

Resumability is intentionally whole-game only. `summaries.jsonl` is the durable
completion marker: completed game/model/condition/mode keys are never recomputed,
while an interrupted game without a summary restarts from decision round 1.
Proposal rows are flushed before the corresponding summary is flushed; orphan
proposals from incomplete attempts are removed before resume and ignored by
analysis. With concurrency `C`, interruption may cause up to `C` in-progress games
to restart and their partial API cost may be incurred again. This tradeoff is
accepted to keep the harness simple; no round/response checkpoints are stored.

Frozen run metadata includes model/config identity, condition, mode, split,
manifest and prompt/benchmark versions, word-list/config hashes, and a stable hash
of the exact selected game IDs. Resume rejects any changed setting or subset.

---

## 17. Information-gain oracle

Information gain is computed deterministically from the current feasible secret set.

Let current feasible secrets be `S_t` and let `g` be a guess in the selected
mode's permitted action space. Partition `S_t` by the feedback pattern that would
result from guessing `g`.

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

### Mode-specific oracle legal-guess set

NORMAL uses `IG*_legal`, maximized over the complete action-valid legal-guess
universe: the full frozen historical legal vocabulary or all 256 dynamic words.
An inconsistent legal guess has a normal information-gain value.

STRICT uses `IG*_strict`, maximized only over action-valid, currently
constraint-consistent legal guesses. A constraint-inconsistent proposal is not a
played action in STRICT, so its played-action IG is missing.

Define:

```text
IG*_mode = max_g IG(g)
```

Cache aggressively. A precomputed feedback-pattern matrix for the historical answer/guess lexicons is acceptable and recommended if needed for performance.

The implementation uses a frozen one-byte-per-pair historical feedback matrix.
Its header binds it to the exact ordered answer and legal-guess vocabularies by
SHA-256. Historical IG memory-maps this artifact; dynamic-256 continues using the
direct deterministic scorer. Matrix lookup must be numerically identical to direct
scoring and does not change the oracle or any experimental semantics.

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

### 18.2 Action and constraint fidelity

#### Initial Action Valid@1 / @3

Action-valid initial top-1 proposals divided by all initial proposals; and
action-valid initial suggestions divided by all three initial slots.

Repairs are excluded from this metric because it measures autonomous constraint maintenance before verifier intervention.

#### Initial Constraint Consistent@1 / @3

Constraint-consistent initial guesses divided by action-valid initial guesses, at
top-1 and across top-three respectively.

#### Initial Strict Valid@1 / @3

`action_valid AND constraint_consistent`, divided by all initial proposals/slots.
These retain approximate comparability with pre-v4 `Valid@1`/`Valid@3`.

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

Compute information gain for suggestions permitted by the selected mode and use
that mode's explicitly named oracle.

#### Top-1 normalized information efficiency

When `IG_star > 0`:

```text
IG_efficiency = IG(g1) / IG*_mode
```

In NORMAL this is available for every action-valid played top-1, including a
constraint violation. In STRICT it is available only for played strict-valid
top-1 actions.

#### Search regret

Among valid suggestions in the top three:

```text
search_regret_mode = IG*_mode - max(IG(mode-permitted top3 suggestions))
```

If none of the top three are valid, this value is missing and the state is already captured by constraint-fidelity metrics.

This measures failure to generate a strategically strong candidate anywhere in the top three.

#### Ranking regret

If top-1 is valid and at least one top-three suggestion is valid:

```text
ranking_regret_mode = max(IG(mode-permitted top3 suggestions)) - IG(g1)
```

This measures whether the model generated a better option but ranked it below its chosen action.

#### Total top-1 regret

When top-1 is valid:

```text
total_regret_mode = IG*_mode - IG(g1)
```

For valid top-1 states:

```text
total_regret = search_regret + ranking_regret
```

assuming the same validity handling and definitions above.

### 18.5 Repair capability

#### RepairSuccess

```text
P(repaired top1 passes selected mode's play gate | repair attempted)
```

Report overall and stratified by initial error class:

- protocol;
- format;
- lexicon;
- constraint (STRICT only).

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
- Initial Action Valid@1/@3;
- Initial Constraint Consistent@1/@3;
- Initial Strict Valid@1/@3;
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
- Initial Action Valid@1 and Initial Strict Valid@1;
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
- Action Valid@1 and Strict Valid@1;
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
game_mode
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

action_status_1
action_status_2
action_status_3
constraint_consistent_1
constraint_consistent_2
constraint_consistent_3
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
ig_oracle
ig_oracle_kind            # legal | strict
ig_efficiency_top1
search_regret
ranking_regret
total_regret

played
played_guess
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
game_mode
model_key
solved
solve_round
round_score              # solve_round or 7
played_guess_count
initial_action_invalid_count
initial_constraint_violation_count
initial_top3_constraint_violation_count
repair_top1_constraint_violation_count
all_suggestion_constraint_violation_count
repair_attempt_count
repair_success_count
forfeit_count
protocol_error_count
format_error_count
lexicon_error_count
constraint_consistent_played_guess_count
constraint_inconsistent_played_guess_count
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
  --mode normal \
  --split dev

# Run one model on evaluation data
python -m benchmark run \
  --model qwen3_8b \
  --condition dynamic_256 \
  --mode strict \
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
(run_id, model_key, condition, game_mode, game_id)
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
│   │   ├── openai_compatible.py
│   │   └── huggingface_nscale.py
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

For Hugging Face/Nscale Qwen runs, additionally record the gateway, exact requested `:nscale` model identifier, returned model identifier when exposed, configured inference provider, base URL, structured-output setting, pricing configuration, and reasoning mode.

Unknown pricing MUST produce `null` estimated costs. Do not record zero cost or use a dollar cost guard until pricing has been explicitly configured.

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
- Hugging Face Inference Providers adapter with Nscale pinned for Qwen;
- token/latency/cost capture;
- transient infrastructure retries;
- concurrency and resume.

### Milestone 5: analysis MVP

- aggregate primary/secondary metrics;
- bootstrap confidence intervals;
- export CSV/Parquet summary tables;
- basic plots for Solve@6, round score, Action Valid@1, Constraint Consistent@1,
  Strict Valid@1, IG efficiency, repair success, and constraint age.

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

The primary benchmark uses Hugging Face Inference Providers with Nscale explicitly pinned for Qwen3 8B, 14B, and 32B. Do not substitute another deployment, provider policy, or Qwen generation without creating a new benchmark version and rerunning all affected comparisons. Fine-tuning remains outside the MVP.

---

## 30. Definition of MVP done

The MVP is complete when all of the following are true:

1. deterministic engine tests pass, including duplicate-letter cases;
2. dev and evaluation manifests can be generated and frozen reproducibly;
3. all three prompts satisfy contamination/naming checks;
4. a mock provider can run the entire game/repair protocol end to end;
5. OpenAI and OpenAI-compatible provider adapters can execute stateless calls;
6. one development game can be run successfully for an OpenAI model;
7. one development game can be run successfully against each configured Hugging Face/Nscale Qwen track;
8. results are resumable and logged without duplicate completed games;
9. the analysis command computes primary metrics plus the agreed behavioral metrics;
10. no evaluation run depends on persistent LLM session state;
11. all run artifacts include prompt/config/manifest hashes.

---

## 31. First instruction to Codex

When beginning implementation, treat this document as the canonical experiment specification.

Before writing provider code, inspect the repository and create a short implementation plan. Then implement Milestones 1-3 first and run the deterministic test suite. Do not spend API money until the deterministic core, manifests, prompt checks, mock provider, and repair protocol pass locally.

Where provider SDK details or exact model identifiers have changed since this document was written, update only the provider/config layer using current official documentation. Do not silently change the experimental conditions, prompts, validation semantics, metrics, game count, or frozen data protocol.
