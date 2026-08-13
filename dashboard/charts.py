from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def metric_comparison(frame: pd.DataFrame, metric: str, *, color: str = "condition") -> go.Figure:
    low, high = f"{metric}_ci_low", f"{metric}_ci_high"
    error = frame[high] - frame[metric] if high in frame else None
    error_minus = frame[metric] - frame[low] if low in frame else None
    figure = px.scatter(
        frame, x="model_key", y=metric, color=color if color in frame else None,
        symbol="game_mode" if "game_mode" in frame else None,
        error_y=error, error_y_minus=error_minus,
        hover_data=[column for column in ("games", "reasoning_setting") if column in frame],
    )
    figure.update_traces(marker_size=11)
    return figure


def forest_plot(
    frame: pd.DataFrame, estimate: str, *, label_columns: tuple[str, ...], title: str,
) -> go.Figure:
    data = frame.copy()
    data["label"] = data[list(label_columns)].astype(str).agg(" · ".join, axis=1)
    figure = go.Figure(go.Scatter(
        x=data[estimate], y=data["label"], mode="markers",
        error_x={"type": "data", "symmetric": False,
                 "array": data["ci_high"] - data[estimate],
                 "arrayminus": data[estimate] - data["ci_low"]},
        customdata=data[[column for column in ("pairs", "pair_complete") if column in data]],
        hovertemplate="%{y}<br>Estimate: %{x:.4f}<extra></extra>",
    ))
    figure.add_vline(x=0, line_dash="dash", line_color="gray")
    figure.update_layout(title=title, yaxis={"autorange": "reversed"})
    return figure


def compute_scatter(frame: pd.DataFrame, x: str, y: str) -> go.Figure:
    return px.scatter(
        frame, x=x, y=y, color="model_key", symbol="game_mode",
        hover_data=[column for column in ("condition", "reasoning_setting", "games") if column in frame],
    )


def constraint_curve(frame: pd.DataFrame, *, x: str, y: str, title: str) -> go.Figure:
    return px.line(
        frame, x=x, y=y, color="model_key", line_dash="game_mode",
        facet_col="condition" if "condition" in frame else None,
        markers=True, title=title,
    )
