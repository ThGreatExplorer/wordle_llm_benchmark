import * as Plot from "npm:@observablehq/plot@0.6.17";

export function metricComparison(data, metric, {width = 900, title = ""} = {}) {
  const low = `${metric}_ci_low`, high = `${metric}_ci_high`;
  return Plot.plot({
    width,
    height: 390,
    marginLeft: 70,
    x: {label: null},
    y: {grid: true, label: metric === "solve_at_6" ? "Solve@6" : metric, percent: metric.includes("at_")},
    color: {legend: true, domain: ["normal", "strict"], range: ["#2563eb", "#e05252"]},
    marks: [
      Plot.ruleY([0], {stroke: "#d8d5cf"}),
      Plot.ruleX(data, {x: "model_key", y1: low, y2: high, stroke: "game_mode"}),
      Plot.dot(data, {x: "model_key", y: metric, fill: "game_mode", stroke: "white", r: 7,
        tip: true, title: d => `${d.model_key} · ${d.condition} · ${d.game_mode}`})
    ],
    caption: title
  });
}
