from __future__ import annotations

import argparse
import os
from pathlib import Path

import streamlit as st

from dashboard.components import coverage_warnings
from dashboard.data import snapshot_token, validate_snapshot
from dashboard.views import explorer, game_explorer, report


def analysis_path() -> Path:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--analysis-dir", type=Path)
    args, _ = parser.parse_known_args()
    return args.analysis_dir or Path(os.environ.get("WORDLE_ANALYSIS_DIR", "results/analysis-openai-eval"))


@st.cache_data(show_spinner=False)
def snapshot_warnings(path: str, token: int) -> list[str]:
    del token
    return validate_snapshot(Path(path))


def main() -> None:
    st.set_page_config(page_title="Wordle LLM Benchmark", page_icon="📊", layout="wide")
    analysis_dir = analysis_path()
    st.sidebar.header("Research Results Portal")
    st.sidebar.caption(str(analysis_dir))
    if st.sidebar.button("Refresh data"):
        st.cache_data.clear()
        st.rerun()
    page = st.sidebar.radio("View", ["Research Report", "Interactive Explorer", "Game Explorer"])
    try:
        token = snapshot_token(analysis_dir)
        coverage_warnings(snapshot_warnings(str(analysis_dir), token))
        {"Research Report": report.render, "Interactive Explorer": explorer.render,
         "Game Explorer": game_explorer.render}[page](analysis_dir)
    except (FileNotFoundError, ValueError) as exc:
        st.error(str(exc))
        st.code(
            "uv run python -m benchmark analyze --results results "
            "--output results/analysis-openai-eval"
        )


main()
