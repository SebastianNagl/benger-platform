#!/usr/bin/env python3
"""Snapshot the holistic baseline (Falllösung) judge prompt into the repo.

The tailored instrument is frozen in data/interim/rubric_prompt_snapshot.json,
but the holistic control arm's prompt lived only as code in benger-extended
(falloesung_constants.py). The matched holistic arms (Luna/Mini ×3) grade with
this exact prompt, so the paper needs a frozen copy with provenance.

Usage: uv run python scripts/ops/snapshot_falloesung_prompt.py
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
EXTENDED_REPO = HERE.parent.parent.parent / "benger-extended"
SOURCE = EXTENDED_REPO / "benger_extended" / "workers" / "falloesung_constants.py"
OUT = HERE / "data" / "interim" / "falloesung_prompt_snapshot.json"


def main() -> int:
    spec = importlib.util.spec_from_file_location("falloesung_constants", SOURCE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # stdlib-only module; no package install needed

    commit = subprocess.run(
        ["git", "-C", str(EXTENDED_REPO), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()

    snapshot = {
        "source_repo": "benger-extended",
        "source_path": str(SOURCE.relative_to(EXTENDED_REPO)),
        "source_commit": commit,
        "retrieved": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "system_prompt": mod.FALLOESUNG_SYSTEM_PROMPT,
        "prompt_template": mod.FALLOESUNG_PROMPT_TEMPLATE,
        "template_slots": ["context", "ground_truth", "prediction"],
        "dimensions": mod.FALLOESUNG_DIMENSIONS,
        "grade_table": mod.FALLOESUNG_GRADE_TABLE,
    }
    OUT.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1), encoding="utf-8")
    total = sum(d["max_score"] for d in mod.FALLOESUNG_DIMENSIONS.values())
    print(f"snapshot -> {OUT.relative_to(HERE)}")
    print(f"  commit {commit[:12]}, {len(mod.FALLOESUNG_DIMENSIONS)} dimensions, "
          f"sum max = {total}, template {len(mod.FALLOESUNG_PROMPT_TEMPLATE)} chars")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
