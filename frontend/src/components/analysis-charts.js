import * as Plot from "npm:@observablehq/plot";

const colors = {normal: "#2563eb", strict: "#e05252", baseline: "#2563eb", medium: "#7357d9"};

export function lineChart(data, {x, y, width, title, color = "model_key"}) {
  return Plot.plot({
    width, height: 330, marginLeft: 58,
    style: {background: "transparent"},
    x: {label: x.replaceAll("_", " ")},
    y: {label: y.replaceAll("_", " "), grid: true},
    color: {legend: true},
    marks: [
      Plot.ruleY([0]),
      Plot.line(data, {x, y, stroke: color, strokeWidth: 2}),
      Plot.dot(data, {x, y, fill: color, r: 4, tip: true, title: d => `${d.model_key} · ${d.condition} · ${d.game_mode}`})
    ],
    caption: title
  });
}

export function computeScatter(data, {x, y, width}) {
  return Plot.plot({
    width, height: 380, marginLeft: 68,
    style: {background: "transparent"},
    x: {label: x.replaceAll("_", " "), grid: true},
    y: {label: y.replaceAll("_", " "), grid: true},
    color: {domain: Object.keys(colors), range: Object.values(colors), legend: true},
    symbol: {legend: true},
    marks: [Plot.dot(data, {
      x, y, fill: "reasoning_setting", symbol: "game_mode", r: 7, opacity: .85, tip: true,
      title: d => `${d.model_key} · ${d.condition} · ${d.game_mode} · ${d.reasoning_setting}`
    })]
  });
}

export function candidateTrajectory(data, {width = 700} = {}) {
  const played = data.filter(d => d.top1_played);
  if (!played.length) return null;
  const points = [{decision_round: 0, candidates: played[0].candidate_count_before},
    ...played.map(d => ({decision_round: d.decision_round, candidates: d.candidate_count_after}))];
  return Plot.plot({
    width, height: 230, marginLeft: 62,
    style: {background: "transparent"},
    x: {label: "Decision round", ticks: 7},
    y: {label: "Feasible secrets", type: "log", grid: true},
    marks: [Plot.line(points, {x: "decision_round", y: "candidates", curve: "step-after", stroke: "#2563eb", strokeWidth: 3}),
      Plot.dot(points, {x: "decision_round", y: "candidates", fill: "#2563eb", r: 4, tip: true})]
  });
}
