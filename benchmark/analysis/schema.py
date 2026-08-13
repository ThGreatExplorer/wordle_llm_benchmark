from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pyarrow.parquet as pq

ANALYSIS_SCHEMA_VERSION = "analysis-v1"
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
REQUIRED_COLUMNS = {
    "metrics": {"model_key", "condition", "game_mode", "reasoning_setting", "split", "games"},
    "coverage": {"run_id", "model_key", "condition", "game_mode", "requested", "completed", "complete"},
    "games": {"run_id", "game_id", "model_key", "condition", "game_mode", "solved", "round_score", "secret"},
    "proposals": {"run_id", "game_id", "decision_round", "proposal_type", "top1", "top1_played"},
}
UNIQUE_KEYS = {
    "coverage": ("run_id",),
    "games": ("run_id", "game_id"),
    "proposals": ("run_id", "game_id", "decision_round", "proposal_type"),
}


def load_analysis_metadata(path: Path) -> dict:
    marker = path / "analysis_metadata.json"
    if not marker.exists():
        raise FileNotFoundError(f"Missing processed snapshot marker: {marker}")
    metadata = json.loads(marker.read_text())
    if metadata.get("analysis_schema_version") != ANALYSIS_SCHEMA_VERSION:
        raise ValueError(f"Unsupported analysis schema: {metadata.get('analysis_schema_version')}")
    return metadata


def analysis_table_path(path: Path, table: str) -> Path:
    if table not in TABLES:
        raise ValueError(f"Unknown processed table: {table}")
    result = path / TABLES[table]
    if not result.exists():
        raise FileNotFoundError(f"Missing processed table: {result}")
    return result


def validate_required_columns(path: Path, table: str) -> None:
    columns = set(pq.read_schema(analysis_table_path(path, table)).names)
    missing = REQUIRED_COLUMNS.get(table, set()) - columns
    if missing:
        raise ValueError(f"{table}.parquet is missing columns: {', '.join(sorted(missing))}")


def validate_unique_keys(path: Path, table: str) -> None:
    keys = UNIQUE_KEYS.get(table)
    if not keys:
        return
    columns = ", ".join(keys)
    source = str(analysis_table_path(path, table)).replace("'", "''")
    query = f"SELECT 1 FROM read_parquet('{source}') GROUP BY {columns} HAVING count(*) > 1 LIMIT 1"
    with duckdb.connect() as connection:
        if connection.execute(query).fetchone():
            raise ValueError(f"{table}.parquet contains duplicate keys")


def validate_analysis_snapshot(path: Path) -> list[str]:
    load_analysis_metadata(path)
    for table in REQUIRED_COLUMNS:
        validate_required_columns(path, table)
        validate_unique_keys(path, table)
    coverage = analysis_table_path(path, "coverage")
    with duckdb.connect() as connection:
        incomplete = connection.execute(
            "SELECT count(*) FROM read_parquet(?) WHERE NOT complete", [str(coverage)]
        ).fetchone()[0]
    return ([f"{incomplete} run(s) are incomplete; comparisons may be provisional."]
            if incomplete else [])
