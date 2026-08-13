from __future__ import annotations

import pandas as pd
import streamlit as st


def metric_filters(frame: pd.DataFrame) -> dict[str, list[str]]:
    columns = st.columns(5)
    result = {}
    for widget, column, label in zip(
        columns, ("model_key", "condition", "game_mode", "reasoning_setting", "split"),
        ("Model", "Condition", "Mode", "Reasoning", "Split"), strict=True,
    ):
        values = sorted(frame[column].dropna().astype(str).unique())
        result[column] = widget.multiselect(label, values, key=f"filter-{column}")
    return result
