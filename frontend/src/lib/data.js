const DIMENSIONS = new Set(["model_key", "model_family", "condition", "game_mode", "reasoning_setting", "split"]);

export function rows(result) {
  const names = result?.schema?.fields?.map(field => field.name);
  return Array.from(result ?? [], row => names
    ? Object.fromEntries(names.map(name => [name, row[name]]))
    : {...row});
}

function literal(value) {
  return `'${String(value).replaceAll("'", "''")}'`;
}

function where(filters = {}) {
  const clauses = Object.entries(filters)
    .filter(([key, value]) => DIMENSIONS.has(key) && value && value !== "all")
    .map(([key, value]) => `${key} = ${literal(value)}`);
  return clauses.length ? ` WHERE ${clauses.join(" AND ")}` : "";
}

export function getMetricSlice(filters = {}) {
  return [`SELECT * FROM metrics${where(filters)} ORDER BY model_key, condition, game_mode, reasoning_setting`];
}

export function getCoverage() {
  return ["SELECT * FROM coverage ORDER BY model_key, condition, game_mode"];
}

export function getContrast(type, filters = {}) {
  const tables = {
    paired: "paired_contrasts", model: "model_contrasts", dynamic: "dynamic_contrasts",
    reasoning: "reasoning_effects", enforcement: "enforcement_penalty",
    penalty_reduction: "penalty_reduction"
  };
  if (!(type in tables)) throw new Error(`Unknown contrast: ${type}`);
  return [`SELECT * FROM ${tables[type]}${where(filters)}`];
}

export function getGames(filters = {}) {
  return [`SELECT * FROM games${where(filters)} ORDER BY run_id, game_id`];
}

export function getGame(runId, gameId) {
  return [`SELECT * FROM games WHERE run_id = ${literal(runId)} AND game_id = ${literal(gameId)}`];
}

export function getGameTrajectory(runId, gameId) {
  return [`SELECT * FROM proposals WHERE run_id = ${literal(runId)} AND game_id = ${literal(gameId)} ORDER BY decision_round, CASE proposal_type WHEN 'initial' THEN 0 ELSE 1 END`];
}

export function getConstraintAge(filters = {}) {
  return [`SELECT * FROM constraint_age${where(filters)} ORDER BY clue_age`];
}

export function getConsistencyByRound(filters = {}) {
  return [`SELECT * FROM consistency_by_round${where(filters)} ORDER BY decision_round`];
}

export function formatPercent(value) {
  return value == null ? "—" : Intl.NumberFormat("en-US", {style: "percent", maximumFractionDigits: 1}).format(value);
}
