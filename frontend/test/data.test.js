import test from "node:test";
import assert from "node:assert/strict";

import {getContrast, getGameTrajectory, getMetricSlice, rows} from "../src/lib/data.js";

test("frontend queries use the stable table contract and escape values", () => {
  assert.equal(getMetricSlice({model_key: "gpt5", condition: "all"})[0],
    "SELECT * FROM metrics WHERE model_key = 'gpt5' ORDER BY model_key, condition, game_mode, reasoning_setting");
  assert.match(getGameTrajectory("run'o", "game-1")[0], /run_id = 'run''o'/);
  assert.throws(() => getContrast("unknown"), /Unknown contrast/);
});

test("DuckDB Arrow results become ordinary row arrays", () => {
  const arrowLike = {*[Symbol.iterator]() {
    yield Object.create({ignored: true}, {model_key: {value: "gpt5", enumerable: true}});
    yield {model_key: "gpt56"};
  }};
  assert.deepEqual(rows(arrowLike), [{model_key: "gpt5"}, {model_key: "gpt56"}]);
});

test("DuckDB Arrow schema materializes non-enumerable fields", () => {
  const row = {};
  Object.defineProperty(row, "game_id", {value: "game-1", enumerable: false});
  const table = Object.assign([row], {schema: {fields: [{name: "game_id"}]}});
  assert.deepEqual(rows(table), [{game_id: "game-1"}]);
});
