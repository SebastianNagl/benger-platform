#!/usr/bin/env python3
"""D6 main-arm rubric selection: PRE-REGISTERED seeded random draw.

Rule (DESIGN.md, fixed 2026-08-04 before any tailored-arm judge data):
per exam, `random.Random(f"benger-transformation-d6-v1:{task_id}")
.choice(sorted(valid rubric ids))` over the contract-valid (v3,
non-archived) rubrics. Activation runs through the extended PATCH endpoint
so the one-active-per-task invariant and the task.data mirror are
maintained by the same code path the app uses.

Writes the draw record to ``data/interim/active_rubric_selection.json``
(exam, pool size, drawn rubric id + generator) for the manuscript.

Usage: uv run python scripts/ops/select_active_rubrics.py \
           --base-url http://api.localhost [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
RUBRICS = HERE / "data" / "raw" / "local" / "task_rubrics.json"
OUT = HERE / "data" / "interim" / "active_rubric_selection.json"
SEED_PREFIX = "benger-transformation-d6-v1"
PROJECT_ID = "e529779b-300f-48c0-89cb-90f3f4b72a51"

sys.path.insert(0, str(HERE / "scripts" / "ops"))
from setup_audit_project import Client  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    rubrics = [
        r
        for r in json.loads(RUBRICS.read_text(encoding="utf-8"))
        if r.get("status") != "archived"
        and (r.get("generation_metadata") or {}).get("contract_version") == 3
    ]
    by_task: dict[str, list] = {}
    for r in rubrics:
        by_task.setdefault(r["task_id"], []).append(r)

    record = []
    for task_id in sorted(by_task):
        pool = sorted(r["id"] for r in by_task[task_id])
        rng = random.Random(f"{SEED_PREFIX}:{task_id}")
        drawn_id = rng.choice(pool)
        drawn = next(r for r in by_task[task_id] if r["id"] == drawn_id)
        record.append(
            {
                "task_id": task_id,
                "pool_size": len(pool),
                "rubric_id": drawn_id,
                "generator_model_id": drawn.get("generator_model_id"),
            }
        )
        print(
            f"{task_id[:8]}: pool {len(pool):2d} -> {drawn_id[:8]} "
            f"({drawn.get('generator_model_id')})"
        )

    OUT.write_text(json.dumps(
        {"seed_prefix": SEED_PREFIX, "selection": record}, indent=2
    ), encoding="utf-8")
    print(f"wrote {OUT.relative_to(HERE)}")
    if args.dry_run:
        return 0

    client = Client(args.base_url)
    client.login("admin@example.com", "admin")
    for row in record:
        client.request(
            "PATCH",
            f"/api/projects/{PROJECT_ID}/bewertungsbogen/{row['rubric_id']}",
            {"action": "activate"},
        )
    print(f"activated {len(record)} rubrics via API")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
