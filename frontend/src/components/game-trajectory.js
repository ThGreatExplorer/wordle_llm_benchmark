import {html} from "npm:htl";

const value = (v, fallback = "—") => v == null ? fallback : v;
const yesNo = v => v == null ? "—" : v ? "yes" : "no";
const bits = v => v == null ? "—" : `${Number(v).toFixed(3)} bits`;

function proposalTable(row) {
  return html`<div class="proposal-table" role="table">
    <div class="proposal-head" role="row"><span>Rank</span><span>Guess</span><span>Action valid</span><span>Consistent</span><span>IG</span></div>
    ${[1, 2, 3].map(rank => html`<div role="row"><span>${rank}</span><strong>${String(value(row[`top${rank}`])).toUpperCase()}</strong><span>${yesNo(row[`top${rank}_action_valid`])}</span><span>${yesNo(row[`top${rank}_constraint_consistent`])}</span><span>${bits(row[`information_gain_top${rank}`])}</span></div>`)}
  </div>`;
}

export function gameTrajectory(rows) {
  if (!rows.length) return html`<div class="empty-board">No proposals were recorded.</div>`;
  const grouped = new Map();
  for (const row of rows) grouped.set(row.decision_round, [...(grouped.get(row.decision_round) ?? []), row]);
  const groups = [...grouped];
  return html`<div class="round-timeline">${groups.map(([round, proposals]) => {
    const played = proposals.find(d => d.top1_played);
    const status = played ? (played.proposal_type === "repair" ? "played after repair" : "played") : "forfeited";
    return html`<details class="round-card" ${round === 1 ? "open" : null}>
      <summary><span>Round ${round}</span><strong class="status-${status.replaceAll(" ", "-")}">${status}</strong><span>${played ? String(played.played_guess).toUpperCase() : "No guess played"}</span></summary>
      ${proposals.map(row => html`<section class="proposal-detail">
        <div class="proposal-title"><h4>${row.proposal_type} proposal</h4><span>${row.top1_played ? "Played" : "Rejected"}</span></div>
        ${proposalTable(row)}
        <div class="diagnostic-grid">
          <div><span>AI top-1 IG</span><strong>${bits(row.information_gain_top1)}</strong></div>
          <div><span>Oracle IG</span><strong>${bits(row.ig_oracle)}</strong></div>
          <div><span>IG efficiency</span><strong>${row.information_gain_top1 != null && row.ig_oracle ? `${(row.information_gain_top1 / row.ig_oracle * 100).toFixed(1)}%` : "—"}</strong></div>
          <div><span>Oracle</span><strong>${value(row.ig_oracle_kind)}</strong></div>
          <div><span>Candidates</span><strong>${Number(row.candidate_count_before).toLocaleString()} → ${row.top1_played ? Number(row.candidate_count_after).toLocaleString() : "unchanged"}</strong></div>
          <div><span>Violated clue ages</span><strong>${Array.from(row.top1_violated_constraint_ages ?? []).join(", ") || "none"}</strong></div>
          <div><span>Reasoning tokens</span><strong>${Number(value(row.reasoning_tokens, 0)).toLocaleString()}</strong></div>
          <div><span>Latency</span><strong>${(Number(value(row.latency_ms, 0)) / 1000).toFixed(2)}s</strong></div>
          <div><span>Cost</span><strong>${row.estimated_cost_usd == null ? "unknown" : `$${Number(row.estimated_cost_usd).toFixed(4)}`}</strong></div>
        </div>
      </section>`)}
    </details>`;
  })}</div>`;
}
