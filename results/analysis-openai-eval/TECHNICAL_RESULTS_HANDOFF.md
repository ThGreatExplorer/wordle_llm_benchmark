# Technical Results Handoff: Wordle LLM Benchmark

## Snapshot and experimental status

This document summarizes the current processed OpenAI evaluation snapshot.

- Benchmark version: `mvp-v4`
- Prompt version: `prompt-v4`
- Analysis schema: `analysis-v1`
- Analysis timestamp: `2026-08-13T03:45:49Z`
- Recorded Git commit: `44d7e4d44f88aa287bf27a4b63baacdc50ca34e3`
- Bootstrap: 10,000 game-level resamples, seed `0`
- Provider: OpenAI
- Models: GPT-4o, GPT-5, GPT-5.6
- Conditions: `hist_named`, `hist_unnamed`, `dynamic_256`
- Modes: `normal`, `strict`

The snapshot contains 2,000 completed of 2,700 requested normal/strict games,
387 solved games, and $35.4891 in recorded completed-game cost. All nine
normal-mode cells are complete. Several strict cells are incomplete, so the
normal-mode analysis is usable while combined normal/strict conclusions remain
provisional.

The Part 1 MVP now consists of the three OpenAI models. Its primary normal-mode
matrix contains 1,350 games. Strict mode is an additional constraint-enforced
experiment. Qwen is deferred to Part 2 and is not included here.

## Protocol semantics

In `normal` mode, every structurally and lexically legal top-1 is played even if
it violates previous feedback. Constraint inconsistency is measured independently
and does not suppress feedback.

In `strict` mode, a constraint-inconsistent top-1 is rejected and receives one
repair attempt. Failed repair forfeits the decision round and produces no feedback.

Important metrics:

- `Solve@6`: fraction solved within six decision rounds.
- Mean score: solve round, with failures scored as 7.
- Action Valid@1: structurally and lexically playable initial top-1.
- Constraint Consistent@1: exact replay consistency among action-valid top-1 guesses.
- Strict Valid@1: action-valid and constraint-consistent.
- IG efficiency: played top-1 information gain divided by the mode-specific oracle.
- Normal uses the full legal-guess oracle; strict uses the strict-consistent oracle.
- Enforcement penalty: `Solve@6_normal - Solve@6_strict`.

## Coverage

| Model | Condition | Normal | Strict |
|---|---|---:|---:|
| GPT-4o | Historical named | 150/150 | 4/150 |
| GPT-4o | Historical unnamed | 150/150 | 96/150 |
| GPT-4o | Dynamic 256 | 150/150 | 4/150 |
| GPT-5 | Historical named | 150/150 | 150/150 |
| GPT-5 | Historical unnamed | 150/150 | 150/150 |
| GPT-5 | Dynamic 256 | 150/150 | 150/150 |
| GPT-5.6 | Historical named | 150/150 | 0/150 |
| GPT-5.6 | Historical unnamed | 150/150 | 0/150 |
| GPT-5.6 | Dynamic 256 | 150/150 | 96/150 |

Consequences:

- All normal-mode model/condition comparisons are usable.
- GPT-5 strict comparisons are complete.
- GPT-4o strict results must not be generalized.
- GPT-5.6 strict historical results do not exist.
- GPT-5.6 dynamic enforcement results are provisional but use 96 paired games.
- Medium-reasoning evaluation results are absent from this snapshot.

## Complete normal-mode results

| Model | Condition | Solve@6 | 95% CI | Mean score | Action Valid@1 | CC@1 | Strict Valid@1 | IG efficiency | Played/game |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| GPT-4o | Hist named | 3.3% | 0.7–6.7% | 6.927 | 99.7% | 20.9% | 20.8% | 0.624 | 5.960 |
| GPT-4o | Hist unnamed | 6.0% | 2.7–10.0% | 6.847 | 99.8% | 23.1% | 23.0% | 0.629 | 5.907 |
| GPT-4o | Dynamic 256 | 8.7% | 4.7–13.3% | 6.767 | 79.8% | 27.1% | 21.6% | 0.642 | 5.213 |
| GPT-5 | Hist named | 6.7% | 2.7–10.7% | 6.787 | 94.9% | 24.8% | 23.6% | 0.637 | 5.793 |
| GPT-5 | Hist unnamed | 6.0% | 2.7–10.0% | 6.813 | 94.8% | 24.6% | 23.3% | 0.634 | 5.827 |
| GPT-5 | Dynamic 256 | 6.0% | 2.7–10.0% | 6.827 | 57.9% | 20.5% | 11.9% | 0.549 | 4.487 |
| GPT-5.6 | Hist named | 58.7% | 50.7–66.7% | 5.520 | 98.2% | 49.7% | 48.8% | 0.765 | 5.100 |
| GPT-5.6 | Hist unnamed | 55.3% | 47.3–63.3% | 5.673 | 98.5% | 47.9% | 47.2% | 0.753 | 5.220 |
| GPT-5.6 | Dynamic 256 | 66.7% | 58.7–74.0% | 5.240 | 83.3% | 41.1% | 34.2% | 0.749 | 4.680 |

`CC@1` means Constraint Consistent@1.

## Main model-generation result

GPT-5.6 is dramatically stronger than both GPT-4o and GPT-5.

| Contrast | Condition | Solve@6 difference | 95% CI |
|---|---|---:|---:|
| GPT-5.6 − GPT-5 | Hist named | +52.0 pp | +42.7 to +61.3 |
| GPT-5.6 − GPT-5 | Hist unnamed | +49.3 pp | +40.7 to +58.0 |
| GPT-5.6 − GPT-5 | Dynamic 256 | +60.7 pp | +52.0 to +68.7 |
| GPT-5.6 − GPT-4o | Hist named | +55.3 pp | +46.7 to +64.0 |
| GPT-5.6 − GPT-4o | Hist unnamed | +49.3 pp | +40.7 to +58.0 |
| GPT-5.6 − GPT-4o | Dynamic 256 | +58.0 pp | +50.0 to +66.0 |

GPT-5 does not materially outperform GPT-4o:

| Condition | GPT-5 − GPT-4o | 95% CI |
|---|---:|---:|
| Hist named | +3.3 pp | −1.3 to +8.7 |
| Hist unnamed | 0.0 pp | −5.3 to +5.3 |
| Dynamic 256 | −2.7 pp | −8.7 to +3.3 |

The expected monotonic GPT-4o → GPT-5 → GPT-5.6 progression does not appear.
GPT-4o and GPT-5 form a similarly weak tier, followed by a discontinuous GPT-5.6
improvement. GPT-5 is numerically worse than GPT-4o dynamically, although its
confidence interval includes zero.

## Action validity and dynamic-pool compliance

Historical Action Valid@1 is nearly perfect for GPT-4o (99.7–99.8%), somewhat
lower for GPT-5 (94.8–94.9%), and 98.2–98.5% for GPT-5.6.

Dynamic legality is substantially harder:

| Model | Dynamic Action Valid@1 | Dynamic lexicon-error rate |
|---|---:|---:|
| GPT-4o | 79.8% | 29.1% |
| GPT-5 | 57.9% | 53.3% |
| GPT-5.6 | 83.3% | 21.5% |

The lexicon-error rate covers logged suggestions and therefore has a different
denominator from Action Valid@1.

GPT-5 has unexpectedly poor dynamic-pool compliance: only 57.9% of initial
top-1 guesses are playable and more than half of logged suggestions are outside
the permitted pool. Supplying the complete 256-word legal universe does not ensure
that the model restricts itself to that universe.

## Constraint consistency collapses after feedback

Round 1 is trivially 100% consistent because no previous clues exist. Consistency
then drops sharply.

### GPT-4o normal Constraint Consistent@1 by round

| Condition | R2 | R3 | R4 | R5 | R6 |
|---|---:|---:|---:|---:|---:|
| Hist named | 17.1% | 3.1% | 0.7% | 0.5% | 1.2% |
| Hist unnamed | 23.8% | 3.6% | 2.5% | 1.4% | 1.0% |
| Dynamic 256 | 13.6% | 5.8% | 3.2% | 3.0% | 4.8% |

### GPT-5 normal Constraint Consistent@1 by round

| Condition | R2 | R3 | R4 | R5 | R6 |
|---|---:|---:|---:|---:|---:|
| Hist named | 23.4% | 6.8% | 4.0% | 1.0% | 1.1% |
| Hist unnamed | 21.8% | 7.0% | 3.1% | 2.6% | 1.3% |
| Dynamic 256 | 22.7% | 13.5% | 8.7% | 4.2% | 4.4% |

### GPT-5.6 normal Constraint Consistent@1 by round

| Condition | R2 | R3 | R4 | R5 | R6 |
|---|---:|---:|---:|---:|---:|
| Hist named | 49.1% | 26.9% | 21.4% | 20.5% | 18.7% |
| Hist unnamed | 49.3% | 26.8% | 22.6% | 25.8% | 19.6% |
| Dynamic 256 | 24.4% | 17.5% | 23.3% | 15.9% | 26.3% |

GPT-4o and GPT-5 approach zero consistency after several clues despite producing
playable historical words. GPT-5.6 retains materially more consistency, but remains
far from reliable.

GPT-5.6's dynamic curve is non-monotonic. This should not be interpreted as automatic
late-round improvement: later rounds contain a selected population of surviving
games with smaller candidate sets.

## Constraint-age behavior

Normal historical violation rates are high and relatively flat across clue ages:

- GPT-4o historical named: approximately 84.8–87.4%.
- GPT-5 historical named: approximately 81.8–84.9%.
- GPT-5.6 historical named: approximately 44.5–57.1%.

There is no strong universal signature in which old clues are uniquely forgotten
while recent clues are preserved. For GPT-4o and GPT-5, failure resembles broad
inability to perform exact replay consistency rather than clean memory decay.

## Naming Wordle does not reliably help

Paired named-minus-unnamed Solve@6 effects:

| Model | Mode | Effect | 95% CI |
|---|---|---:|---:|
| GPT-4o | Normal | −2.7 pp | −5.3 to −0.7 |
| GPT-5 | Normal | +0.7 pp | −4.0 to +5.3 |
| GPT-5 | Strict | −2.7 pp | −8.0 to +2.0 |
| GPT-5.6 | Normal | +3.3 pp | −6.0 to +12.7 |

GPT-4o is the only complete contrast excluding zero, and it runs opposite to the
expected naming benefit. A plausible hypothesis is that explicit naming activates
conventional Wordle heuristics or memorized openings that are poorly matched to the
benchmark protocol. This is model-specific evidence, not proof that naming generally
harms performance.

## Dynamic/OOD behavior is not uniformly harder

Historical-unnamed minus dynamic Solve@6:

| Model | Mode | Effect | 95% CI |
|---|---|---:|---:|
| GPT-4o | Normal | −2.7 pp | −8.7 to +3.3 |
| GPT-5 | Normal | 0.0 pp | −5.3 to +5.3 |
| GPT-5 | Strict | +4.7 pp | 0.0 to +10.0 |
| GPT-5.6 | Normal | −11.3 pp | −22.0 to 0.0 |

Negative values mean dynamic performance was higher. GPT-5.6 performs best on
`dynamic_256` (66.7%), versus 58.7% historical named and 55.3% historical unnamed.
This contradicts a simple OOD-degradation expectation.

Two forces likely compete:

1. Dynamic vocabulary and pool adherence make action generation harder.
2. The 256-secret universe makes search and final identification easier.

For GPT-5.6, the smaller hypothesis space appears to dominate. For GPT-5, severe
outside-pool errors may cancel the search-space advantage. Dynamic and historical
secrets are not paired, so causal claims require caution.

## Information-seeking strategy

Normal-mode IG efficiency:

| Model | Hist named | Hist unnamed | Dynamic |
|---|---:|---:|---:|
| GPT-4o | 0.624 | 0.629 | 0.642 |
| GPT-5 | 0.637 | 0.634 | 0.549 |
| GPT-5.6 | 0.765 | 0.753 | 0.749 |

Normal-mode total regret:

| Model | Hist named | Hist unnamed | Dynamic |
|---|---:|---:|---:|
| GPT-4o | 0.606 | 0.628 | 0.701 |
| GPT-5 | 0.599 | 0.609 | 0.724 |
| GPT-5.6 | 0.399 | 0.429 | 0.283 |

GPT-5.6 combines higher information efficiency and lower regret with better solving.
Its dynamic advantage is especially notable: it has the highest Solve@6 and lowest
total regret despite imperfect action validity and constraint consistency.

GPT-5's dynamic weakness combines pool noncompliance with poorer search quality.

## Repeated guesses

| Model | Hist named | Hist unnamed | Dynamic |
|---|---:|---:|---:|
| GPT-4o | 4.7% | 4.8% | 3.2% |
| GPT-5 | 3.2% | 5.1% | 15.6% |
| GPT-5.6 | 0.0% | 0.4% | 0.7% |

GPT-5's 15.6% dynamic repeat rate is a major deviation. Repeated legal guesses are
played in normal mode but usually provide no new information. This likely contributes
to its poor dynamic performance alongside outside-pool errors and low IG efficiency.

## Strict enforcement and feedback starvation

Complete GPT-5 enforcement comparisons:

| Condition | Normal Solve@6 | Strict Solve@6 | Penalty | 95% CI | Strict forfeits/game |
|---|---:|---:|---:|---:|---:|
| Hist named | 6.7% | 4.7% | +2.0 pp | −2.0 to +6.7 | 4.347 |
| Hist unnamed | 6.0% | 7.3% | −1.3 pp | −6.7 to +4.0 | 4.240 |
| Dynamic 256 | 6.0% | 2.7% | +3.3 pp | −1.3 to +8.0 | 4.680 |

None of GPT-5's solve penalties clearly differs from zero, but strict mode radically
changes gameplay. Normal GPT-5 plays approximately 4.5–5.8 guesses/game, while strict
GPT-5 plays only 1.25–1.61 and forfeits more than four rounds/game. Strict repair
success is only 3.4–11.9%.

For GPT-5.6 dynamic, based on 96 paired games:

- Paired normal Solve@6: 63.5%
- Strict Solve@6: 35.4%
- Enforcement penalty: 28.1 pp
- 95% CI: 17.7–38.5 pp
- Score penalty: +0.635
- Strict forfeits/game: 3.344

This is a strong provisional signal, but the run is incomplete.

Strict enforcement creates the anticipated feedback-starvation mechanism: a
constraint violation triggers repair, repair commonly fails, the round is forfeited,
and no new feedback arrives. For weak solvers, both modes are near the floor, masking
the interaction penalty. GPT-5.6 is strong enough for the penalty to become visible.

Strict IG efficiency is often numerically higher than normal IG efficiency. This does
not demonstrate globally better strategy: strict mode uses a smaller oracle universe
and only played strict-valid guesses receive played-action IG. Direct cross-mode IG
comparisons are affected by action-space and selection differences.

## Repair behavior

Normal historical repair is rare and usually successful:

- GPT-4o: 100% in the few observed attempts.
- GPT-5: approximately 80–85%.
- GPT-5.6: approximately 92%.

Normal dynamic repair is harder:

- GPT-4o: 45.8%.
- GPT-5: 43.5%.
- GPT-5.6: 72.4%.

Strict repair success is much lower because constraint inconsistency becomes a repair
trigger: GPT-5 historical is 3.4–4.6%, GPT-5 dynamic is 11.9%, and provisional
GPT-5.6 dynamic is 18.5%.

## Cost

Normal-mode mean cost per game:

| Model | Hist named | Hist unnamed | Dynamic |
|---|---:|---:|---:|
| GPT-4o | $0.0099 | $0.0099 | $0.0204 |
| GPT-5 | $0.0070 | $0.0070 | $0.0146 |
| GPT-5.6 | $0.0192 | $0.0198 | $0.0352 |

GPT-5.6 costs roughly 2.7–2.8 times GPT-5 historically and 2.4 times GPT-5
dynamically, but improves Solve@6 by approximately 49–61 percentage points. Its cost
per solved game may therefore be substantially better despite higher per-game cost.
Dynamic prompts approximately double cost because they include all 256 legal words.

## Reasoning-medium experiment status

The reasoning-effect and penalty-reduction tables are empty. There is no evaluation
evidence yet for medium reasoning, reasoning-token treatment effects, or whether
reasoning reduces strict enforcement penalties. Development smoke runs must not be
presented as evaluation results.

GPT-5 baseline `minimal` and GPT-5.6 baseline `none` are baseline configurations,
not the medium-reasoning treatment.

## Strongest defensible findings

1. GPT-5.6 outperforms GPT-4o and GPT-5 by approximately 49–61 percentage points.
2. GPT-5 does not clearly outperform GPT-4o.
3. Accumulated constraint consistency is a major bottleneck.
4. GPT-5.6 improves both constraint maintenance and information-seeking strategy.
5. Naming Wordle does not reliably help; GPT-4o shows a significant negative effect.
6. Dynamic 256 is not uniformly harder; GPT-5.6 performs best dynamically.
7. GPT-5 is exceptionally poor at obeying the supplied dynamic legal universe.
8. Strict enforcement creates frequent forfeits and feedback starvation.
9. GPT-5.6 has a large provisional dynamic enforcement penalty of 28.1 pp.
10. Reasoning-ablation conclusions are not yet available.

## Claims that should not yet be made

Do not claim:

- final strict results for GPT-4o or GPT-5.6;
- a final overall enforcement penalty;
- that medium reasoning helps or hurts;
- that naming generally harms performance;
- that dynamic evaluation is intrinsically easier;
- that strict mode improves strategy;
- that constraint errors specifically reflect memory decay;
- any Qwen comparison;
- a final aggregate result across all requested games.

## Recommended next steps

1. Finish incomplete GPT-4o and GPT-5.6 strict runs.
2. Regenerate the processed snapshot.
3. Complete GPT-5 and GPT-5.6 medium-reasoning evaluation runs.
4. Inspect GPT-5 dynamic outside-pool guesses, repetitions, repairs, and candidate trajectories.
5. Test whether GPT-5.6's dynamic advantage persists after controlling for candidate count and lexical validity.
6. Analyze consistency conditional on round survival to separate behavior from survivor selection.
7. Keep normal and strict IG results separate because their oracle universes differ.
8. Treat GPT-4o's negative naming effect as a focused model-specific result.
