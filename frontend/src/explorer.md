---
title: Experiment Lab
toc: false
sql:
  metrics: ./data/analysis/metrics.parquet
  paired_contrasts: ./data/analysis/contrasts/paired.parquet
  model_contrasts: ./data/analysis/contrasts/model.parquet
  dynamic_contrasts: ./data/analysis/contrasts/dynamic.parquet
  reasoning_effects: ./data/analysis/contrasts/reasoning.parquet
  enforcement_penalty: ./data/analysis/contrasts/enforcement_penalty.parquet
  penalty_reduction: ./data/analysis/contrasts/penalty_reduction.parquet
  constraint_age: ./data/analysis/diagnostics/constraint_age.parquet
  consistency_by_round: ./data/analysis/diagnostics/consistency_by_round.parquet
  coverage: ./data/analysis/run_coverage.parquet
---

```js
import {getMetricSlice, getContrast, getConstraintAge, getConsistencyByRound, getCoverage, rows, formatPercent} from "./lib/data.js";
import {metricComparison} from "./components/metric-comparison.js";
import {forestPlot} from "./components/forest-plot.js";
import {lineChart, computeScatter} from "./components/analysis-charts.js";
import {metricHelp} from "./components/metric-help.js";
import * as Inputs from "npm:@observablehq/inputs@0.12.0";
const definitions = await FileAttachment("./data/analysis/metrics.json").json();
const allMetrics = rows(await sql(getMetricSlice()));
const coverage = rows(await sql(getCoverage()));
const metricOptions = Object.keys(definitions).filter(metric => metric in (allMetrics[0] ?? {}));
```

<nav class="site-nav"><a href="/">Research Report</a><a href="/explorer">Experiment Lab</a><a href="/games">Game Inspector</a></nav>

# Experiment Lab

<p class="dek">Slice the same deterministic analysis used by the report. Every panel shares one experiment selection; missing combinations are shown explicitly.</p>

```js
const filters = view(Inputs.form({
  model: Inputs.select(["all", ...new Set(allMetrics.map(d => d.model_key))], {label: "Model"}),
  condition: Inputs.select(["all", ...new Set(allMetrics.map(d => d.condition))], {label: "Condition"}),
  mode: Inputs.select(["all", "normal", "strict"], {label: "Mode"}),
  reasoning: Inputs.select(["all", ...new Set(allMetrics.map(d => d.reasoning_setting))], {label: "Reasoning"}),
  split: Inputs.select(["all", ...new Set(allMetrics.map(d => d.split))], {label: "Split"}),
  metric: Inputs.select(metricOptions, {label: "Metric", value: "solve_at_6"})
}, {template: inputs => html`<div class="filter-bar">${Object.values(inputs)}</div>`}));
```

```js
const dimensions = {model_key: filters.model, condition: filters.condition, game_mode: filters.mode, reasoning_setting: filters.reasoning, split: filters.split};
const slice = rows(await sql(getMetricSlice(dimensions)));
const selectedDefinition = metricHelp(filters.metric, definitions);
const comparisonWorkspace = slice.length ? html`<div class="chart-grid">
  <div class="chart-panel"><h3>Models and conditions</h3>${resize(width => metricComparison(slice, filters.metric, {width}))}</div>
  <div class="chart-panel"><h3>Performance and cost</h3>${resize(width => computeScatter(slice.filter(d => d.mean_cost_usd_per_game != null && d[filters.metric] != null), {x: "mean_cost_usd_per_game", y: filters.metric, width}))}</div>
</div>` : html`<div class="chart-panel">No data available for this combination.</div>`;
```

<div class="lab-intro">
  ${selectedDefinition}
  <div class="stat-grid compact-stats">
    <div class="metric-card"><span>Rows in slice</span><strong>${slice.length}</strong></div>
    <div class="metric-card"><span>Games represented</span><strong>${d3.sum(slice, d => d.games).toLocaleString()}</strong></div>
    <div class="metric-card"><span>Best observed</span><strong>${slice.length ? formatPercent(d3.max(slice, d => d[filters.metric])) : "—"}</strong></div>
  </div>
</div>

## Comparison workspace

${comparisonWorkspace}

## Contrast Lab

```js
const contrastChoice = view(Inputs.select(["paired", "model", "dynamic", "reasoning", "enforcement", "penalty_reduction"], {label: "Contrast family"}));
```
```js
const contrastRows = rows(await sql(getContrast(contrastChoice))).filter(d =>
  Object.entries(dimensions).every(([key, selected]) => selected === "all" || !(key in d) || d[key] === selected));
const contrastConfig = {
  paired: ["delta", "ci_low", "ci_high"], model: ["delta", "ci_low", "ci_high"],
  dynamic: ["delta_hist_unnamed_minus_dynamic", "ci_low", "ci_high"],
  reasoning: ["delta_medium_minus_baseline", "ci_low", "ci_high"],
  enforcement: ["solve_penalty", "solve_ci_low", "solve_ci_high"],
  penalty_reduction: ["penalty_reduction", "ci_low", "ci_high"]
}[contrastChoice];
const contrastMetricRows = contrastRows.filter(d => !d.metric || d.metric === filters.metric).map(d => ({
  ...d, estimate: d[contrastConfig[0]], ci_low: d[contrastConfig[1]], ci_high: d[contrastConfig[2]],
  label: [d.model_key ?? d.model_family, d.left_model && `${d.left_model} vs ${d.right_model}`, d.condition, d.game_mode, d.contrast].filter(Boolean).join(" · ")
})).filter(d => d.estimate != null && d.ci_low != null && d.ci_high != null);
const contrastPanel = contrastMetricRows.length
  ? html`<div class="chart-panel">${resize(width => forestPlot(contrastMetricRows, {estimate: "estimate", label: "label", width}))}<p class="chart-note">Zero means no measured difference. Incomplete comparisons remain provisional.</p></div>`
  : html`<div class="chart-panel">No matching paired contrast is available.</div>`;
```

${contrastPanel}

## Constraint behavior

```js
const diagnosticDimensions = {model_key: filters.model, condition: filters.condition, game_mode: filters.mode, split: filters.split};
const age = rows(await sql(getConstraintAge(diagnosticDimensions)));
const rounds = rows(await sql(getConsistencyByRound(diagnosticDimensions)));
```

<div class="chart-grid">
  <div class="chart-panel"><h3>Violation probability by clue age</h3>${age.length ? resize(width => lineChart(age, {x: "clue_age", y: "violation_rate", width, color: "model_key"})) : "No data available."}</div>
  <div class="chart-panel"><h3>Consistency by decision round</h3>${rounds.length ? resize(width => lineChart(rounds, {x: "decision_round", y: "consistency_rate", width, color: "model_key"})) : "No data available."}</div>
</div>
<p class="interpretation-text"><strong>Interpretation:</strong> These curves describe when accumulated constraints fail. They do not establish why a model failed, and normal/strict histories can diverge after rejected guesses.</p>

## Compute efficiency

```js
const computeAxes = view(Inputs.form({
  x: Inputs.select(["mean_cost_usd_per_game", "mean_reasoning_tokens_per_game", "mean_latency_ms_per_game"], {label: "Compute axis"}),
  y: Inputs.select(["solve_at_6", "constraint_consistent_at_1", "ig_efficiency"], {label: "Outcome axis"})
}, {template: inputs => html`<div class="inline-controls">${Object.values(inputs)}</div>`}));
```
```js
const computeRows = slice.filter(d => d[computeAxes.x] != null && d[computeAxes.y] != null);
const computePanel = computeRows.length ? html`<div class="chart-panel">${resize(width => computeScatter(computeRows, {...computeAxes, width}))}</div>` : html`<div class="chart-panel">No compute data is available for this slice.</div>`;
```

${computePanel}

## Run coverage and data quality

```js
const coverageSlice = coverage.filter(d =>
  (filters.model === "all" || d.model_key === filters.model) &&
  (filters.condition === "all" || d.condition === filters.condition) &&
  (filters.mode === "all" || d.game_mode === filters.mode) &&
  (filters.split === "all" || d.split === filters.split));
const coverageRequested = d3.sum(coverageSlice, d => d.requested);
const coverageCompleted = d3.sum(coverageSlice, d => d.completed);
const coveragePanel = html`<div class="coverage-summary ${coverageCompleted < coverageRequested ? "coverage-warning" : ""}">
  <div><span>Requested</span><strong>${coverageRequested.toLocaleString()}</strong></div>
  <div><span>Completed</span><strong>${coverageCompleted.toLocaleString()}</strong></div>
  <div><span>Missing</span><strong>${(coverageRequested - coverageCompleted).toLocaleString()}</strong></div>
  <div><span>Coverage</span><strong>${coverageRequested ? formatPercent(coverageCompleted / coverageRequested) : "—"}</strong></div>
</div>`;
```

${coveragePanel}
${coverageCompleted < coverageRequested ? html`<p class="caveat-text"><strong>Provisional:</strong> this slice contains incomplete runs. Paired contrasts expose their own pair counts and completeness state.</p>` : html`<p class="interpretation-text">Every requested game in this slice has a durable completed summary.</p>`}
