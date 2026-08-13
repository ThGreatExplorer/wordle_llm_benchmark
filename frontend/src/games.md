---
title: Game Inspector
toc: false
sql:
  games: ./data/analysis/games.parquet
  proposals: ./data/analysis/proposals.parquet
---

```js
import {getGames, getGameTrajectory, rows} from "./lib/data.js";
import {wordleBoard} from "./components/wordle-board.js";
import {gameList} from "./components/game-list.js";
import {gameTrajectory} from "./components/game-trajectory.js";
import {candidateTrajectory} from "./components/analysis-charts.js";
import * as Inputs from "npm:@observablehq/inputs@0.12.0";

const games = rows(await sql(getGames({split: "eval"})));
const models = ["all", ...new Set(games.map(d => d.model_key))];
const conditions = ["all", ...new Set(games.map(d => d.condition))];
const modes = ["all", ...new Set(games.map(d => d.game_mode))];
const reasoningSettings = ["all", ...new Set(games.map(d => d.reasoning_setting))];
```

<nav class="site-nav"><a href="/">Research Report</a><a href="/explorer">Experiment Lab</a><a href="/games">Game Inspector</a></nav>

# Game Inspector

<p class="dek">Select a completed benchmark game to inspect every played guess and its deterministic feedback. Repairs and forfeited rounds are shown as part of the board state.</p>

```js
const filters = view(Inputs.form({
  search: Inputs.text({label: "Search game ID or secret", placeholder: "e.g. hist_eval_0042"}),
  model: Inputs.select(models, {label: "Model"}),
  condition: Inputs.select(conditions, {label: "Condition"}),
  mode: Inputs.select(modes, {label: "Mode"}),
  reasoning: Inputs.select(reasoningSettings, {label: "Reasoning"}),
  result: Inputs.select(["all", "solved", "unsolved"], {label: "Result"}),
  score: Inputs.select(["all", 1, 2, 3, 4, 5, 6, 7], {label: "Score"}),
  violations: Inputs.checkbox(["yes"], {label: "Has constraint violation"}),
  repairs: Inputs.checkbox(["yes"], {label: "Used repair"}),
  minimumReasoning: Inputs.number({label: "Minimum reasoning tokens", min: 0, value: 0}),
  minimumCost: Inputs.number({label: "Minimum cost (USD)", min: 0, value: 0, step: .01})
}, {template: inputs => html`<div class="filter-bar">${Object.values(inputs)}</div>`}));
```

```js
const query = String(filters.search ?? "").trim().toLowerCase();
const filteredGames = games.filter(d =>
  (!query || d.game_id.toLowerCase().includes(query) || d.secret.toLowerCase().includes(query)) &&
  (filters.model === "all" || d.model_key === filters.model) &&
  (filters.condition === "all" || d.condition === filters.condition) &&
  (filters.mode === "all" || d.game_mode === filters.mode) &&
  (filters.reasoning === "all" || d.reasoning_setting === filters.reasoning) &&
  (filters.result === "all" || Boolean(d.solved) === (filters.result === "solved")) &&
  (filters.score === "all" || Number(d.round_score) === Number(filters.score)) &&
  (!filters.violations.length || d.initial_constraint_violation_count > 0) &&
  (!filters.repairs.length || d.repair_attempt_count > 0) &&
  Number(d.reasoning_tokens_total ?? 0) >= Number(filters.minimumReasoning ?? 0) &&
  Number(d.estimated_cost_usd_total ?? 0) >= Number(filters.minimumCost ?? 0)
);
```

```js
const gameKey = view(gameList(filteredGames));
```

```js
const gameChoice = filteredGames.find(d => `${d.run_id}:${d.game_id}` === gameKey);
const trajectory = gameChoice ? rows(await sql(getGameTrajectory(gameChoice.run_id, gameChoice.game_id))) : [];
const inspector = gameChoice ? html`<div class="game-inspector">
  <main class="game-detail">
    <header class="game-summary selected-game-header">
      <p class="eyebrow">Selected game</p>
      <h2>${gameChoice.game_id}</h2>
      <div class="stat-grid">
        <div class="metric-card"><span>Model</span><strong>${gameChoice.model_key}</strong></div>
        <div class="metric-card"><span>Secret</span><strong>${gameChoice.secret.toUpperCase()}</strong></div>
        <div class="metric-card"><span>Score</span><strong>${gameChoice.round_score}</strong></div>
        <div class="metric-card"><span>Result</span><strong>${gameChoice.solved ? "Solved" : "Unsolved"}</strong></div>
      </div>
    </header>
    <section class="inspector-section board-section">
      <div class="inspector-heading"><p class="eyebrow">Game replay</p><h3>Played trajectory</h3><p>Every played guess and its deterministic feedback.</p></div>
      <div class="board-frame">${wordleBoard(trajectory)}</div>
    </section>
    <section class="inspector-section candidate-section">
      <div class="inspector-heading"><p class="eyebrow">Search space</p><h3>Candidate-space trajectory</h3><p>Feasible secrets remaining after each played guess.</p></div>
      <div class="chart-frame">${resize(width => candidateTrajectory(trajectory, {width}) ?? html`<p>No played guesses.</p>`)}</div>
    </section>
    <section class="inspector-section diagnostics-section">
      <div class="inspector-heading"><p class="eyebrow">Decision audit</p><h3>Round diagnostics</h3><p>Open a round to compare the model's ranked guesses, oracle information gain, validity, and compute.</p></div>
      ${gameTrajectory(trajectory)}
    </section>
  </main>
</div>` : html`<div class="chart-panel">No games match these filters.</div>`;
```

${inspector}
