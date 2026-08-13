import {html} from "npm:htl";

export function metricHelp(metric, definitions) {
  const item = definitions[metric];
  if (!item) return html`<aside class="metric-help"><strong>${metric}</strong><p>No explanation is available.</p></aside>`;
  return html`<aside class="metric-help">
    <p class="eyebrow">What does this measure?</p><h3>${item.title}</h3>
    <dl><dt>Definition</dt><dd>${item.definition}</dd><dt>Why it matters</dt><dd>${item.why_it_matters}</dd><dt>Direction</dt><dd>${item.direction}</dd></dl>
    ${(item.caveats ?? []).map(caveat => html`<p class="caveat-text"><strong>Caveat:</strong> ${caveat}</p>`)}
  </aside>`;
}
