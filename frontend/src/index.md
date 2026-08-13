---
title: Research Report
toc: false
sql:
  metrics: ./data/analysis/metrics.parquet
  coverage: ./data/analysis/run_coverage.parquet
  enforcement_penalty: ./data/analysis/contrasts/enforcement_penalty.parquet
  paired_contrasts: ./data/analysis/contrasts/paired.parquet
  dynamic_contrasts: ./data/analysis/contrasts/dynamic.parquet
  reasoning_effects: ./data/analysis/contrasts/reasoning.parquet
  penalty_reduction: ./data/analysis/contrasts/penalty_reduction.parquet
  games: ./data/analysis/games.parquet
  proposals: ./data/analysis/proposals.parquet
---

```js
import {getCoverage, getMetricSlice, getContrast, getGames, getGameTrajectory, formatPercent, rows} from "./lib/data.js";
import {metricComparison} from "./components/metric-comparison.js";
import {forestPlot} from "./components/forest-plot.js";
import {findingCard} from "./components/finding-card.js";
import {wordleBoard} from "./components/wordle-board.js";
import {computeScatter} from "./components/analysis-charts.js";
import * as Inputs from "npm:@observablehq/inputs@0.12.0";

const snapshot = await FileAttachment("./data/analysis/snapshot.json").json();
const metadata = await FileAttachment("./data/analysis/analysis_metadata.json").json();
const findings = await FileAttachment("./data/analysis/findings.json").json();
const caveats = await FileAttachment("./data/analysis/caveats.json").json();
const coverage = rows(await sql(getCoverage()));
const completed = d3.sum(coverage, d => d.completed);
const requested = d3.sum(coverage, d => d.requested);
const spend = d3.sum(coverage, d => d.recorded_cost_usd);
const modelCount = new Set(coverage.map(d => d.model_key)).size;
const allBaseline = rows(await sql(getMetricSlice({split: "eval", reasoning_setting: "baseline"})));
const bestSolve = d3.greatest(allBaseline, d => d.solve_at_6);
const largestConstraintGap = d3.greatest(allBaseline, d => (d.initial_action_valid_at_1 ?? 0) - (d.constraint_consistent_at_1 ?? 0));
const enforcement = rows(await sql(getContrast("enforcement", {reasoning_setting: "baseline"})));
const largestPenalty = d3.greatest(enforcement, d => d.solve_penalty);
const namedEffects = rows(await sql(getContrast("paired"))).filter(d => d.metric === "solve_at_6");
const dynamicEffects = rows(await sql(getContrast("dynamic"))).filter(d => d.metric === "solve_at_6");
const reasoningEffects = rows(await sql(getContrast("reasoning"))).filter(d => d.metric === "solve_at_6");
```

<nav class="site-nav"><a href="/">Research Report</a><a href="/explorer">Experiment Lab</a><a href="/games">Game Inspector</a></nav>

<header class="hero">
  <div>
    <p class="eyebrow">Wordle LLM Benchmark · Research Report</p>
    <h1>Do LLMs Actually Reason About Wordle? <span>A Contamination-Resistant Benchmark for Multi-Turn Constraint Tracking</span></h1>
    <div class="research-questions">
      <p><strong>RQ1</strong> How does multi-turn word-constraint reasoning vary across frontier and legacy language models?</p>
      <p><strong>RQ2</strong> How much does recognizing the task as Wordle improve performance?</p>
      <p><strong>RQ3</strong> Does changing Wordle from a fixed historical answer distribution to dynamically generated candidate spaces reduce frontier-model saturation?</p>
      <p><strong>RQ4</strong> How does changing from inference to reasoning affect performance?</p>
    </div>
  </div>
  <aside class="status-panel">
    <p class="eyebrow">Current analysis snapshot</p>
    <dl>
      <dt>Completed games</dt><dd>${completed.toLocaleString()} / ${requested.toLocaleString()}</dd>
      <dt>Models represented</dt><dd>${modelCount}</dd>
      <dt>Recorded spend</dt><dd>${spend.toLocaleString("en-US", {style: "currency", currency: "USD"})}</dd>
      <dt>Coverage</dt><dd>${formatPercent(completed / requested)}</dd>
    </dl>
    ${snapshot.warnings.length ? html`<p class="caveat-text">${snapshot.warnings.join(" ")}</p>` : html`<p>Complete snapshot</p>`}
  </aside>
</header>

<section class="section">
  <div class="section-heading"><span class="section-number">00</span><div><h2>Three signals worth attention</h2><p>These are descriptive results from the current snapshot. Because coverage is still incomplete, treat them as leads for investigation rather than final claims.</p></div></div>
  <div class="headline-findings">
    <article class="metric-card"><span>Highest observed Solve@6</span><strong class="finding-number">${formatPercent(bestSolve?.solve_at_6)}</strong><p>${bestSolve?.model_key} · ${bestSolve?.condition} · ${bestSolve?.game_mode}</p></article>
    <article class="metric-card"><span>Largest action–constraint gap</span><strong class="finding-number">${formatPercent((largestConstraintGap?.initial_action_valid_at_1 ?? 0) - (largestConstraintGap?.constraint_consistent_at_1 ?? 0))}</strong><p>${largestConstraintGap?.model_key} produces legal actions more reliably than clue-consistent ones.</p></article>
    <article class="metric-card"><span>Largest strict enforcement penalty</span><strong class="finding-number">${formatPercent(largestPenalty?.solve_penalty)}</strong><p>${largestPenalty?.model_family} · ${largestPenalty?.condition}; normal minus strict Solve@6.</p></article>
  </div>
</section>

<section class="section">
  <div class="section-heading"><span class="section-number">01</span><div><h2>Model capability</h2><p>Switch conditions to compare the same frozen model tracks and execution modes. Points show Solve@6; intervals are deterministic game-level bootstrap estimates from Python.</p></div></div>
</section>

```js
const reportCondition = view(Inputs.radio(["hist_named", "hist_unnamed", "dynamic_256"], {label: "Condition", value: "hist_named"}));
```
```js
const reportMetrics = rows(await sql(getMetricSlice({condition: reportCondition, split: "eval", reasoning_setting: "baseline"})));
```

<section class="section report-chart-section">
  <div class="chart-panel">${resize(width => metricComparison(reportMetrics, "solve_at_6", {width, title: `${reportCondition} · baseline inference`}))}</div>
</section>

```js
const enforcementRows = enforcement.map(d => ({...d, label: `${d.model_family} · ${d.condition}`, ci_low: d.solve_ci_low, ci_high: d.solve_ci_high}));
```

<section class="section">
  <div class="section-heading"><span class="section-number">02</span><div><h2>The cost of strict enforcement</h2><p>Positive values indicate that normal mode solved more games than strict mode. Zero remains visually explicit; incomplete pairs are not treated as final evidence.</p></div></div>
  <div class="chart-panel">${resize(width => forestPlot(enforcementRows, {estimate: "solve_penalty", label: "label", width}))}</div>
</section>

```js
const findingSpec = findings.find(d => d.id === "enforcement_penalty");
const findingEvidence = enforcement.find(d => d.model_family === "gpt5" && d.condition === "hist_named" && d.reasoning_setting === "baseline");
const findingComplete = Boolean(findingEvidence?.pair_complete);
const findingResult = findingEvidence
  ? `The estimated normal-minus-strict Solve@6 penalty is ${formatPercent(findingEvidence.solve_penalty)} (${formatPercent(findingEvidence.solve_ci_low)} to ${formatPercent(findingEvidence.solve_ci_high)}).`
  : "No matching comparison is available in this snapshot.";
```

<section class="section">
  ${findingCard({title: findingSpec.title, result: findingResult, interpretation: findingSpec.interpretation, complete: findingComplete, caveats: findingSpec.caveats.map(id => caveats[id].text)})}
</section>

```js
const reportContrasts = [
  {number: "03", title: "Does naming Wordle matter?", dek: "Paired named-minus-unnamed Solve@6 effects isolate the task-name cue while holding historical games fixed.", data: namedEffects.map(d => ({...d, label: `${d.model_key} · ${d.game_mode}`})), estimate: "delta"},
  {number: "04", title: "The dynamic candidate-space effect", dek: "Historical unnamed minus dynamic Solve@6. This condition comparison is descriptive rather than game-ID paired.", data: dynamicEffects.map(d => ({...d, label: `${d.model_key} · ${d.game_mode}`})), estimate: "delta_hist_unnamed_minus_dynamic"},
  {number: "05", title: "Inference-time reasoning", dek: "Medium-reasoning minus baseline Solve@6 for matched GPT-5 and GPT-5.6 games where available.", data: reasoningEffects.map(d => ({...d, label: `${d.model_family} · ${d.condition} · ${d.game_mode}`})), estimate: "delta_medium_minus_baseline"}
];
const reportContrastSections = html`<div class="report-contrasts">${reportContrasts.filter(item => item.data.length).map(item => html`<section class="section">
  <div class="section-heading"><span class="section-number">${item.number}</span><div><h2>${item.title}</h2><p>${item.dek}</p></div></div>
  <div class="chart-panel">${resize(width => forestPlot(item.data, {estimate: item.estimate, label: "label", width}))}</div>
</section>`)}</div>`;
```

${reportContrastSections}

<section class="section">
  <div class="section-heading"><span class="section-number">06</span><div><h2>Compute efficiency</h2><p>Cost, latency, and realized reasoning tokens are part of the scientific result—not merely billing metadata.</p></div></div>
  <div class="chart-grid">
    <div class="chart-panel"><h3>Solve@6 versus cost per game</h3>${resize(width => computeScatter(allBaseline.filter(d => d.mean_cost_usd_per_game != null), {x: "mean_cost_usd_per_game", y: "solve_at_6", width}))}</div>
    <div class="chart-panel"><h3>Constraint consistency versus reasoning tokens</h3>${resize(width => computeScatter(allBaseline.filter(d => d.mean_reasoning_tokens_per_game != null), {x: "mean_reasoning_tokens_per_game", y: "constraint_consistent_at_1", width}))}</div>
  </div>
</section>

```js
const sampleGames = rows(await sql(getGames({condition: "dynamic_256", game_mode: "normal", split: "eval"})));
const sampleGame = sampleGames[0];
const sampleTrajectory = sampleGame ? rows(await sql(getGameTrajectory(sampleGame.run_id, sampleGame.game_id))) : [];
const sampleInspector = sampleGame ? html`<div class="game-slice">
  <div class="game-summary"><p class="eyebrow">Selected game</p><h3>${sampleGame.game_id}</h3>
    <div class="stat-grid"><div class="metric-card"><span>Model</span><strong>${sampleGame.model_key}</strong></div><div class="metric-card"><span>Secret</span><strong>${sampleGame.secret.toUpperCase()}</strong></div><div class="metric-card"><span>Score</span><strong>${sampleGame.round_score}</strong></div><div class="metric-card"><span>Mode</span><strong>${sampleGame.game_mode}</strong></div></div>
  </div><div class="game-summary">${wordleBoard(sampleTrajectory)}</div>
</div>` : html`<p>No completed game is available.</p>`;
const caveatCards = html`<div class="caveat-grid">${Object.values(caveats).map(item => html`<article class="caveat-card"><h3>${item.title}</h3><p>${item.text}</p></article>`)}</div>`;
```

<section class="section">
  <div class="section-heading"><span class="section-number">07</span><div><h2>Inspect the game, not the log</h2><p>A real completed trajectory rendered as an accessible Wordle board. Repairs and forfeits are first-class states; no hidden chain-of-thought is shown.</p></div></div>
  ${sampleInspector}
</section>

<section class="section">
  <div class="section-heading"><span class="section-number">08</span><div><h2>Limitations and provenance</h2><p>Definitions and results are deterministic; interpretations and caveats are explicitly human-authored.</p></div></div>
  ${caveatCards}
  <details class="provenance"><summary>Data provenance</summary><p>Analysis ${metadata.analysis_schema_version}, generated ${metadata.generated_at_utc}. Benchmark ${metadata.benchmark_versions?.join(", ")}; prompt ${metadata.prompt_versions?.join(", ")}; ${metadata.bootstrap_resamples?.toLocaleString()} bootstrap resamples.</p><p>Snapshot: ${snapshot.source}</p></details>
</section>

<section class="section conclusion"><p class="eyebrow">Conclusion</p><h2>Solving and constraint discipline are different capabilities.</h2><p>Normal mode measures whether a model can continue solving after a constraint mistake. Strict mode measures whether it can solve while every accumulated clue is enforced. Their difference is itself an experimental result.</p></section>
