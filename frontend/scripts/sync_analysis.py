from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import yaml

from benchmark.analysis.schema import TABLES, validate_analysis_snapshot

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(os.environ.get("WORDLE_ANALYSIS_DIR", ROOT / "results/analysis-openai-eval")).resolve()
TARGET = ROOT / "frontend/src/data/analysis"
CONTENT = ROOT / "analysis/interpretation"


def main() -> None:
    warnings = validate_analysis_snapshot(SOURCE)
    if TARGET.exists():
        shutil.rmtree(TARGET)
    TARGET.mkdir(parents=True)
    for relative in TABLES.values():
        source, target = SOURCE / relative, TARGET / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    shutil.copy2(SOURCE / "analysis_metadata.json", TARGET / "analysis_metadata.json")
    for name in ("metrics", "findings", "caveats"):
        data = yaml.safe_load((CONTENT / f"{name}.yaml").read_text())
        (TARGET / f"{name}.json").write_text(json.dumps(data, indent=2) + "\n")
    (TARGET / "snapshot.json").write_text(json.dumps({
        "source": str(SOURCE), "warnings": warnings,
    }, indent=2) + "\n")
    print(f"synced validated analysis snapshot from {SOURCE}")


if __name__ == "__main__":
    main()
