import * as Plot from "npm:@observablehq/plot@0.6.17";

export function forestPlot(data, {estimate, low = "ci_low", high = "ci_high", label, width = 900}) {
  return Plot.plot({
    width,
    height: Math.max(250, data.length * 38 + 80),
    marginLeft: 190,
    x: {grid: true, label: "Difference (percentage points)", percent: true},
    y: {label: null},
    marks: [
      Plot.ruleX([0], {stroke: "#837f78", strokeDasharray: "4,4"}),
      Plot.ruleY(data, {y: label, x1: low, x2: high, stroke: "#7357d9", strokeWidth: 2}),
      Plot.dot(data, {y: label, x: estimate, fill: "#7357d9", r: 6, tip: true})
    ]
  });
}
