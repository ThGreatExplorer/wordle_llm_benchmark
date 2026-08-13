from __future__ import annotations

from pathlib import Path

import streamlit as st

from dashboard.charts import compute_scatter, constraint_curve, forest_plot, metric_comparison
from dashboard.components import metric_explainer
from dashboard.content import load_content, metric_help
from dashboard.data import filter_frame, filter_metrics, load_table
from dashboard.filters import metric_filters


def render(analysis_dir: Path) -> None:
    st.title("Interactive Explorer")
    all_metrics = load_table(analysis_dir, "metrics")
    filters = metric_filters(all_metrics)
    frame = filter_metrics(analysis_dir, filters)
    metric_options = [column for column in load_content("metrics") if column in frame]
    metric = st.selectbox("Metric", metric_options)
    metric_explainer(metric_help(metric))
    if frame.empty:
        st.info("No data available for this combination")
        return

    overview, contrasts, constraints, compute = st.tabs(
        ["Comparisons", "Contrasts", "Constraint behavior", "Compute / cost"]
    )
    with overview:
        st.plotly_chart(metric_comparison(frame, metric), width="stretch")
        st.dataframe(frame, width="stretch", hide_index=True)
    with contrasts:
        table_name = st.selectbox(
            "Contrast", ["paired", "model", "dynamic", "reasoning", "enforcement", "penalty_reduction"]
        )
        contrast = load_table(analysis_dir, table_name)
        contrast = filter_frame(contrast, filters)
        if "metric" in contrast:
            contrast = contrast.loc[contrast["metric"] == metric]
        estimates = {
            "paired": "delta", "model": "delta", "dynamic": "delta_hist_unnamed_minus_dynamic",
            "reasoning": "delta_medium_minus_baseline", "enforcement": "solve_penalty",
            "penalty_reduction": "penalty_reduction",
        }
        estimate = estimates[table_name]
        if contrast.empty or estimate not in contrast or "ci_low" not in contrast:
            st.info("No data available for this combination")
        else:
            labels = tuple(column for column in
                           ("model_key", "model_family", "left_model", "right_model", "condition", "game_mode")
                           if column in contrast)
            st.plotly_chart(forest_plot(contrast.dropna(subset=[estimate, "ci_low", "ci_high"]), estimate,
                                        label_columns=labels, title=table_name.replace("_", " ").title()),
                            width="stretch")
            st.dataframe(contrast, width="stretch", hide_index=True)
    with constraints:
        age = load_table(analysis_dir, "constraint_age")
        rounds = load_table(analysis_dir, "consistency_by_round")
        age, rounds = filter_frame(age, filters), filter_frame(rounds, filters)
        if age.empty or rounds.empty:
            st.info("No data available for this combination")
            return
        st.plotly_chart(constraint_curve(age, x="clue_age", y="violation_rate",
                                         title="Violation probability by clue age"), width="stretch")
        st.plotly_chart(constraint_curve(rounds, x="decision_round", y="consistency_rate",
                                         title="Constraint consistency by round"), width="stretch")
    with compute:
        x = st.selectbox("Compute axis", ["mean_cost_usd_per_game", "mean_reasoning_tokens_per_game",
                                          "mean_latency_ms_per_game"])
        y = st.selectbox("Performance axis", ["solve_at_6", "constraint_consistent_at_1", "ig_efficiency"])
        available = frame.dropna(subset=[x, y])
        if available.empty:
            st.info("No data available for this combination")
        else:
            st.plotly_chart(compute_scatter(available, x, y), width="stretch")
