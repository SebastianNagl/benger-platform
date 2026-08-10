#!/usr/bin/env python3
"""Pre-registered seeded draw over the few-shot rubric pool (WP A4).

Rule (DESIGN.md 2026-08-06, fixed before the sweep judged): per clone exam,
random.Random(f"benger-transformation-fewshot-v1:{clone_task_id}").choice(
sorted(schema-conformant few-shot rubric ids)). Schema-conformant = the
clone's task_rubrics with prompt_key='bewertungsbogen_fewshot',
contract_version=3, status != 'archived'. No activation here — the judge
driver activates transiently per exam.

Reads the pool live from the clone DB (few-shot rubrics live on the clone,
not in the source task_rubrics.json). Writes the draw + per-exam pool sizes
to data/interim/fewshot/selection.json.

Usage: uv run python scripts/ops/select_fewshot_rubrics.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
FEWSHOT = HERE / "data" / "interim" / "fewshot"
CLONE_PROJECT = "81e474b8-d226-4bf8-bc2e-fb744d25cba5"
SEED_PREFIX = "benger-transformation-fewshot-v1"


def _psql_json(query):
    out = subprocess.run(
        ["docker", "exec", "benger-db-1", "psql", "-U", "postgres", "-d", "benger",
         "-tAc", f"select coalesce(json_agg(t), '[]') from ({query}) t;"],
        capture_output=True, text=True, check=True).stdout.strip()
    return json.loads(out)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    FEWSHOT.mkdir(parents=True, exist_ok=True)

    rows = _psql_json(
        "select tr.id, tr.task_id, tr.generator_model_id, "
        "(select count(*) from jsonb_object_keys(tr.criteria::jsonb) k) as steps "
        "from task_rubrics tr "
        f"where tr.project_id = '{CLONE_PROJECT}' "
        "and tr.prompt_key = 'bewertungsbogen_fewshot' "
        "and tr.status <> 'archived' "
        "and tr.generation_metadata->>'contract_version' = '3'")
    by_task = defaultdict(list)
    for r in rows:
        by_task[r["task_id"]].append(r)

    record = []
    for task_id in sorted(by_task):
        pool = sorted(r["id"] for r in by_task[task_id])
        drawn_id = random.Random(f"{SEED_PREFIX}:{task_id}").choice(pool)
        drawn = next(r for r in by_task[task_id] if r["id"] == drawn_id)
        record.append({"task_id": task_id, "pool_size": len(pool), "rubric_id": drawn_id,
                       "generator_model_id": drawn["generator_model_id"], "steps": drawn["steps"]})
        print(f"{task_id[:8]}: pool {len(pool):2d} -> {drawn_id[:8]} "
              f"({drawn['generator_model_id'].split('/')[-1]}, {drawn['steps']} steps)")

    print(f"\n{len(record)} exams with a few-shot pool "
          f"(pool sizes: {sorted(r['pool_size'] for r in record)})")
    if len(record) < 15:
        print(f"WARNING: only {len(record)}/15 exams have a schema-conformant few-shot rubric")

    if not args.dry_run:
        (FEWSHOT / "selection.json").write_text(
            json.dumps({"seed_prefix": SEED_PREFIX, "selection": record}, indent=1),
            encoding="utf-8")
        print(f"wrote {FEWSHOT / 'selection.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
