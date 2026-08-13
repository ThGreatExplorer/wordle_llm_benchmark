from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from dashboard.charts import compute_scatter, forest_plot, metric_comparison
from dashboard.content import load_content
from dashboard.data import load_metadata, load_table


def _finding_card(finding: dict, tables: dict[str, pd.DataFrame], caveats: dict) -> None:
    evidence = finding["evidence"]
    frame = tables.get(evidence["table"], pd.DataFrame())
    if evidence.get("metric") and "metric" in frame:
        frame = frame.loc[frame["metric"] == evidence["metric"]]
    for column, value in evidence.get("filters", {}).items():
        if column in frame:
            frame = frame.loc[frame[column] == value]
    with st.container(border=True):
        st.subheader(finding["title"])
        if frame.empty:
            st.markdown("**Result**  \nNo data available yet.")
            return
        row = frame.iloc[0]
        estimate = row.get(evidence["estimate"])
        st.markdown(f"**Result**  \n{finding['result_template'].format(estimate=estimate)}")
        complete = bool(row.get(evidence.get("completeness", ""), True))
        if complete:
            st.markdown(f"**Interpretation**  \n{finding['interpretation']}")
        else:
            st.markdown("**Interpretation**  \nWithheld until the referenced comparison is complete.")
        for caveat_id in finding.get("caveats", []):
            st.markdown(f"**Caveat — {caveats[caveat_id]['title']}**  \n{caveats[caveat_id]['text']}")


def render(analysis_dir: Path) -> None:
    st.title("Wordle LLM Benchmark")
    st.caption("A reproducible study of solving, accumulated constraint reasoning, and inference-time compute.")
    metrics = load_table(analysis_dir, "metrics")
    coverage = load_table(analysis_dir, "coverage")
    tables = {name: load_table(analysis_dir, name) for name in
              ("paired", "dynamic", "reasoning", "enforcement", "penalty_reduction")}
    metadata = load_metadata(analysis_dir)

    st.header("Executive Summary")
    complete = int(coverage["completed"].sum())
    requested = int(coverage["requested"].fillna(0).sum())
    a, b, c = st.columns(3)
    a.metric("Completed games", f"{complete:,}", f"{complete - requested:,} remaining")
    b.metric("Runs represented", len(coverage))
    c.metric("Recorded cost", f"${coverage['recorded_cost_usd'].sum():,.2f}")
    if not bool(coverage["complete"].all()):
        st.warning("This is a provisional snapshot: one or more benchmark runs are incomplete.")
    with st.expander("Run Coverage / Data Quality"):
        st.dataframe(coverage, width="stretch", hide_index=True)

    st.header("Research Questions and Experimental Design")
    st.markdown("""
1. How do model generations differ in solving and accumulated lexical-constraint reasoning?
2. What changes when the task is named, moved to a dynamic candidate space, or strictly enforced?
3. Does medium inference-time reasoning improve performance or reduce enforcement penalties?
""")

    st.header("Main Results")
    st.plotly_chart(metric_comparison(metrics, "solve_at_6"), width="stretch")
    st.header("Constraint Reasoning")
    st.plotly_chart(metric_comparison(metrics, "constraint_consistent_at_1"), width="stretch")

    st.header("Normal vs Strict Enforcement")
    enforcement = tables["enforcement"].dropna(subset=["solve_penalty"])
    if not enforcement.empty:
        st.plotly_chart(forest_plot(
            enforcement.rename(columns={"solve_ci_low": "ci_low", "solve_ci_high": "ci_high"}),
            "solve_penalty", label_columns=("model_family", "condition", "reasoning_setting"),
            title="Solve enforcement penalty",
        ), width="stretch")
    else:
        st.info("No enforcement comparison is available yet.")

    st.header("Named vs Unnamed Effect")
    named = tables["paired"].loc[tables["paired"]["metric"] == "solve_at_6"]
    if not named.empty:
        st.plotly_chart(forest_plot(named, "delta", label_columns=("model_key", "game_mode"),
                                    title="Named − unnamed Solve@6"), width="stretch")
    else:
        st.info("No named/unnamed comparison is available yet.")

    st.header("Dynamic / OOD Effect")
    dynamic = tables["dynamic"].loc[tables["dynamic"]["metric"] == "solve_at_6"]
    if not dynamic.empty:
        st.plotly_chart(forest_plot(dynamic, "delta_hist_unnamed_minus_dynamic",
                                    label_columns=("model_key", "game_mode"),
                                    title="Historical unnamed − dynamic Solve@6"), width="stretch")
    else:
        st.info("No dynamic comparison is available yet.")

    st.header("Reasoning Effects")
    reasoning = tables["reasoning"].loc[tables["reasoning"]["metric"] == "solve_at_6"]
    if not reasoning.empty:
        st.plotly_chart(forest_plot(reasoning, "delta_medium_minus_baseline",
                                    label_columns=("model_family", "condition", "game_mode"),
                                    title="Medium reasoning − baseline Solve@6"), width="stretch")
    else:
        st.info("No paired reasoning comparison is available yet.")

    st.header("Compute / Cost Efficiency")
    compute = metrics.dropna(subset=["mean_cost_usd_per_game", "solve_at_6"])
    if not compute.empty:
        st.plotly_chart(compute_scatter(compute, "mean_cost_usd_per_game", "solve_at_6"), width="stretch")

    st.header("Key Findings")
    caveats = load_content("caveats")
    for finding in load_content("findings"):
        _finding_card(finding, tables, caveats)

    st.header("Caveats / Limitations")
    for caveat in caveats.values():
        st.markdown(f"**{caveat['title']}** — {caveat['text']}")

    st.header("Data Provenance")
    st.json(metadata, expanded=False)

    st.header("Conclusions")
    st.markdown("Curated conclusions above are shown only when their referenced comparison is complete; use the explorer for provisional slices.")
