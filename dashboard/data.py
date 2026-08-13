from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import streamlit as st

TABLES = {
    "metrics": "metrics.parquet",
    "coverage": "run_coverage.parquet",
    "games": "games.parquet",
    "proposals": "proposals.parquet",
    "paired": "contrasts/paired.parquet",
    "model": "contrasts/model.parquet",
    "dynamic": "contrasts/dynamic.parquet",
    "reasoning": "contrasts/reasoning.parquet",
    "enforcement": "contrasts/enforcement_penalty.parquet",
    "penalty_reduction": "contrasts/penalty_reduction.parquet",
    "constraint_age": "diagnostics/constraint_age.parquet",
    "consistency_by_round": "diagnostics/consistency_by_round.parquet",
}
REQUIRED = {
    "metrics": {"model_key", "condition", "game_mode", "reasoning_setting", "split", "games"},
    "coverage": {"run_id", "model_key", "condition", "game_mode", "requested", "completed", "complete"},
    "games": {"run_id", "game_id", "model_key", "condition", "game_mode", "solved", "round_score"},
    "proposals": {"run_id", "game_id", "decision_round", "proposal_type", "top1", "top1_played"},
}


def snapshot_token(analysis_dir: Path) -> int:
    path = analysis_dir / "analysis_metadata.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing processed snapshot marker: {path}")
    return path.stat().st_mtime_ns


def load_metadata(analysis_dir: Path) -> dict[str, Any]:
    path = analysis_dir / "analysis_metadata.json"
    data = json.loads(path.read_text())
    if data.get("analysis_schema_version") != "analysis-v1":
        raise ValueError(f"Unsupported analysis schema: {data.get('analysis_schema_version')}")
    return data


def _path(analysis_dir: Path, table: str) -> Path:
    if table not in TABLES:
        raise ValueError(f"Unknown processed table: {table}")
    path = analysis_dir / TABLES[table]
    if not path.exists():
        raise FileNotFoundError(f"Missing processed table: {path}")
    return path


@st.cache_data(show_spinner=False)
def _cached_query(path: str, table: str, where: str, params: tuple[Any, ...], token: int) -> pd.DataFrame:
    del token
    query = f"SELECT * FROM read_parquet(?)" + (f" WHERE {where}" if where else "")
    with duckdb.connect() as connection:
        frame = connection.execute(query, [path, *params]).df()
    missing = REQUIRED.get(table, set()) - set(frame.columns)
    if missing:
        raise ValueError(f"{table}.parquet is missing columns: {', '.join(sorted(missing))}")
    return frame


def _query(analysis_dir: Path, table: str, where: str = "", params: list[Any] | None = None) -> pd.DataFrame:
    path = _path(analysis_dir, table)
    return _cached_query(str(path), table, where, tuple(params or []), snapshot_token(analysis_dir))


def load_table(analysis_dir: Path, table: str) -> pd.DataFrame:
    return _query(analysis_dir, table)


def filter_metrics(analysis_dir: Path, filters: dict[str, list[str]]) -> pd.DataFrame:
    clauses, params = [], []
    for column in ("model_key", "condition", "game_mode", "reasoning_setting", "split"):
        values = filters.get(column, [])
        if values:
            clauses.append(f"{column} IN ({','.join('?' for _ in values)})")
            params.extend(values)
    return _query(analysis_dir, "metrics", " AND ".join(clauses), params)


def filter_games(analysis_dir: Path, filters: dict[str, Any]) -> pd.DataFrame:
    clauses, params = [], []
    for column in ("model_key", "condition", "game_mode", "reasoning_setting", "split"):
        values = filters.get(column, [])
        if values:
            clauses.append(f"{column} IN ({','.join('?' for _ in values)})")
            params.extend(values)
    if filters.get("solved") is not None:
        clauses.append("solved = ?")
        params.append(filters["solved"])
    if filters.get("minimum_cost") is not None:
        clauses.append("estimated_cost_usd_total >= ?")
        params.append(filters["minimum_cost"])
    if filters.get("minimum_reasoning_tokens") is not None:
        clauses.append("reasoning_tokens_total >= ?")
        params.append(filters["minimum_reasoning_tokens"])
    return _query(analysis_dir, "games", " AND ".join(clauses), params)


def filter_frame(frame: pd.DataFrame, filters: dict[str, list[str]]) -> pd.DataFrame:
    result = frame
    aliases = {"reasoning_setting": ("reasoning_setting", "reasoning_effort")}
    for requested, values in filters.items():
        column = next((name for name in aliases.get(requested, (requested,)) if name in result), None)
        if values and column:
            result = result.loc[result[column].astype(str).isin(values)]
    return result


def load_game_proposals(analysis_dir: Path, run_id: str, game_id: str) -> pd.DataFrame:
    frame = _query(analysis_dir, "proposals", "run_id = ? AND game_id = ?", [run_id, game_id])
    if frame.duplicated(["run_id", "game_id", "decision_round", "proposal_type"]).any():
        raise ValueError("Duplicate proposal trajectory keys")
    order = pd.Categorical(frame["proposal_type"], ["initial", "repair"], ordered=True)
    return frame.assign(_proposal_order=order).sort_values(
        ["decision_round", "_proposal_order"]
    ).drop(columns="_proposal_order")


def validate_snapshot(analysis_dir: Path) -> list[str]:
    load_metadata(analysis_dir)
    warnings = []
    for table in REQUIRED:
        frame = _query(analysis_dir, table)
        keys = {
            "coverage": ["run_id"], "games": ["run_id", "game_id"],
            "proposals": ["run_id", "game_id", "decision_round", "proposal_type"],
        }.get(table)
        if keys and frame.duplicated(keys).any():
            raise ValueError(f"{table}.parquet contains duplicate keys")
    coverage = _query(analysis_dir, "coverage")
    incomplete = coverage.loc[~coverage["complete"]]
    if not incomplete.empty:
        warnings.append(f"{len(incomplete)} run(s) are incomplete; comparisons may be provisional.")
    return warnings
