from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_dashboard(
    metrics: list[dict[str, Any]], ages: list[dict[str, Any]],
    contrasts: list[dict[str, Any]], path: Path,
) -> None:
    data = json.dumps({"metrics": metrics, "ages": ages, "contrasts": contrasts}).replace("</", "<\\/")
    path.write_text("""<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Wordle LLM Benchmark Dashboard</title>
<style>
:root{font:15px system-ui;color:#172033;background:#f4f7fb}body{max-width:1200px;margin:auto;padding:24px}h1{margin:0 0 6px}.muted{color:#667085}.controls,.cards{display:flex;gap:12px;flex-wrap:wrap;margin:22px 0}.controls label{display:grid;gap:5px;font-weight:600}select{padding:8px;border:1px solid #cbd5e1;border-radius:7px;background:white}.card,.panel{background:white;border:1px solid #e2e8f0;border-radius:10px;padding:16px;box-shadow:0 1px 2px #0001}.card{min-width:150px}.card strong{display:block;font-size:24px;margin-top:5px}.panel{margin:14px 0;overflow:auto}svg{min-width:700px}table{border-collapse:collapse;width:100%;font-size:13px}th,td{padding:8px;border-bottom:1px solid #e2e8f0;text-align:right;white-space:nowrap}th{cursor:pointer;background:#f8fafc}th:first-child,th:nth-child(2),td:first-child,td:nth-child(2){text-align:left}.bar{fill:#4c78a8}.ci{stroke:#172033;stroke-width:2}.axis{stroke:#94a3b8}.empty{padding:50px;text-align:center;color:#667085}
</style>
<body><h1>Wordle LLM Benchmark</h1><div class="muted">Interactive aggregate results; filters apply to charts and tables.</div>
<div class="controls"><label>Model<select id="model"></select></label><label>Condition<select id="condition"></select></label><label>Metric<select id="metric"></select></label></div>
<div class="cards"><div class="card">Groups<strong id="groups">0</strong></div><div class="card">Games<strong id="games">0</strong></div><div class="card">Mean value<strong id="average">—</strong></div></div>
<div class="panel"><h2 id="chartTitle">Metric</h2><div id="chart"></div></div>
<div class="panel"><h2>Metrics</h2><table id="table"></table></div>
<div class="panel"><h2>Paired historical contrasts</h2><table id="contrasts"></table></div>
<script id="data" type="application/json">""" + data + """</script>
<script>
const D=JSON.parse(document.getElementById('data').textContent);
const metricNames=['solve_at_6','mean_round_score','initial_valid_at_1','initial_valid_at_3','ig_efficiency','search_regret','ranking_regret','repair_success_rate','forfeit_rate','constraint_age'];
const $=id=>document.getElementById(id), fmt=v=>v==null?'—':Number(v).toFixed(4), esc=v=>String(v).replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]));
function options(id,values){$(id).innerHTML='<option value="*">All</option>'+values.map(v=>`<option>${esc(v)}</option>`).join('')}
options('model',[...new Set(D.metrics.map(x=>x.model_key))]); options('condition',[...new Set(D.metrics.map(x=>x.condition))]);
$('metric').innerHTML=metricNames.map(v=>`<option>${v}</option>`).join('');
function filtered(rows){return rows.filter(x=>($('model').value==='*'||x.model_key===$('model').value)&&($('condition').value==='*'||x.condition===$('condition').value))}
function table(id,rows,cols){const el=$(id); if(!rows.length){el.innerHTML='<tr><td class="empty">No matching data</td></tr>';return} el.innerHTML='<thead><tr>'+cols.map(c=>`<th data-c="${c}">${esc(c)}</th>`).join('')+'</tr></thead><tbody>'+rows.map(r=>'<tr>'+cols.map(c=>`<td>${typeof r[c]==='number'?fmt(r[c]):esc(r[c]??'—')}</td>`).join('')+'</tr>').join('')+'</tbody>'; el.querySelectorAll('th').forEach(th=>th.onclick=()=>{const c=th.dataset.c;rows.sort((a,b)=>typeof a[c]==='number'?(a[c]??Infinity)-(b[c]??Infinity):String(a[c]??'').localeCompare(String(b[c]??'')));table(id,rows,cols)})}
function chart(rows,metric){if(!rows.length){$('chart').innerHTML='<div class="empty">No matching data</div>';return}const vals=rows.map(r=>r[metric]).filter(v=>v!=null), max=Math.max(...vals.map(Math.abs),1), w=900,h=55+rows.length*34;let s=`<svg viewBox="0 0 ${w} ${h}" role="img"><line class="axis" x1="260" y1="30" x2="260" y2="${h-10}"/>`;rows.forEach((r,i)=>{const v=r[metric],y=42+i*34;if(v==null)return;const bw=560*Math.abs(v)/max,lo=r[metric+'_ci_low'],hi=r[metric+'_ci_high'];s+=`<text x="5" y="${y+15}">${esc(r.model_key+' '+r.condition)}</text><rect class="bar" x="260" y="${y}" width="${bw}" height="20"/><text x="${270+bw}" y="${y+15}">${fmt(v)}</text>`;if(lo!=null&&hi!=null){const x1=260+560*Math.abs(lo)/max,x2=260+560*Math.abs(hi)/max;s+=`<line class="ci" x1="${x1}" y1="${y+10}" x2="${x2}" y2="${y+10}"/><line class="ci" x1="${x1}" y1="${y+5}" x2="${x1}" y2="${y+15}"/><line class="ci" x1="${x2}" y1="${y+5}" x2="${x2}" y2="${y+15}"/>`}});$('chart').innerHTML=s+'</svg>'}
function ageChart(rows){if(!rows.length){$('chart').innerHTML='<div class="empty">No clue-age exposures</div>';return}const maxAge=Math.max(...rows.map(x=>x.clue_age)),w=900,h=400,groups=[...new Set(rows.map(x=>x.model_key+' '+x.condition))],colors=['#4c78a8','#f58518','#54a24b','#e45756','#72b7b2','#b279a2'];let s=`<svg viewBox="0 0 ${w} ${h}"><line class="axis" x1="60" y1="350" x2="850" y2="350"/><line class="axis" x1="60" y1="30" x2="60" y2="350"/>`;groups.forEach((g,gi)=>{const pts=rows.filter(x=>x.model_key+' '+x.condition===g&&x.violation_rate!=null).map(x=>`${60+760*x.clue_age/maxAge},${350-300*x.violation_rate}`).join(' ');s+=`<polyline fill="none" stroke="${colors[gi%colors.length]}" stroke-width="3" points="${pts}"/><text x="650" y="${30+gi*18}" fill="${colors[gi%colors.length]}">${esc(g)}</text>`});$('chart').innerHTML=s+'</svg>'}
function render(){const rows=filtered(D.metrics),metric=$('metric').value;$('groups').textContent=rows.length;$('games').textContent=rows.reduce((n,r)=>n+r.games,0);const vals=rows.map(r=>r[metric]).filter(v=>typeof v==='number');$('average').textContent=fmt(vals.length?vals.reduce((a,b)=>a+b,0)/vals.length:null);$('chartTitle').textContent=metric==='constraint_age'?'Constraint violation by clue age':metric;metric==='constraint_age'?ageChart(filtered(D.ages)):chart(rows,metric);table('table',rows,['model_key','condition','games',...metricNames.filter(x=>x!=='constraint_age')]);table('contrasts',D.contrasts.filter(x=>($('model').value==='*'||x.model_key===$('model').value)),['model_key','metric','pairs','delta','ci_low','ci_high'])}
['model','condition','metric'].forEach(id=>$(id).onchange=render);render();
</script></body></html>""")
