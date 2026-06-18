#!/usr/bin/env python3
"""Normalize existing `korrektur_falloesung` task_evaluations to a 0–1 `value`.

Human Falllösung grades used to persist `metrics.korrektur_falloesung.value` as
the RAW 0–100 rubric total (e.g. 11.0, 15.0), unlike `llm_judge_falloesung`
which stores `raw_score / 100` (0–1). The scoring code now normalizes at write
time (`korrektur.py`: `value = total_score / 100.0`); this backfills the rows
written before that change so every consumer (results matrix, annotator
leaderboard, renderers) sees one 0–1 scale.

Strictly value-only + idempotent. Targets the unified-shape rows whose
`value` still equals `details.raw_score` (i.e. not yet divided) and rewrites
`value = raw_score / 100`. After the rewrite `value != raw_score` (for any
raw_score > 0), so a second run is a no-op; the only fixed point is
raw_score == 0 (0/100 == 0, harmless). It NEVER touches `details` (raw_score,
grade_points, dimensions stay as-is), and no other metric or row is read.

FIPS-safe: pure jsonb numeric arithmetic, no md5 (prod Postgres has FIPS
OpenSSL — md5() raises there).

Usage (inside the api container):
  python /app/scripts/backfill_korrektur_falloesung_normalize.py --dry-run
  python /app/scripts/backfill_korrektur_falloesung_normalize.py --apply
"""

from __future__ import annotations

import argparse
import os
import sys

# Make database.py importable whether run as /app/scripts/<f>.py in the
# container or piped via stdin (cwd may not be /app then).
_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in ("/app", os.path.dirname(_HERE)):
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

from sqlalchemy import text  # noqa: E402

from database import get_db  # noqa: E402


# Unified-shape rows whose value has NOT yet been normalized: value still
# equals the raw 0–100 total. (Legacy non-object korrektur blobs, if any,
# are skipped — they carry no `value`/`details.raw_score` pair.)
PREDICATE = """
    jsonb_typeof(metrics->'korrektur_falloesung') = 'object'
    AND metrics->'korrektur_falloesung'->>'value' IS NOT NULL
    AND metrics->'korrektur_falloesung'->'details'->>'raw_score' IS NOT NULL
    AND (metrics->'korrektur_falloesung'->>'value')::numeric
        = (metrics->'korrektur_falloesung'->'details'->>'raw_score')::numeric
    AND (metrics->'korrektur_falloesung'->'details'->>'raw_score')::numeric > 0
"""


def _count(db) -> int:
    return db.execute(
        text(f"SELECT COUNT(*) FROM task_evaluations WHERE {PREDICATE}")
    ).scalar() or 0


def _print_dry_run_summary(db) -> int:
    total = _count(db)
    print(f"rows to normalize (value still == raw 0–100 total): {total}")
    if total == 0:
        return 0
    print()
    print("per project_id:")
    rows = db.execute(text(f"""
        SELECT t.project_id::text AS project_id, COUNT(*) AS n
        FROM task_evaluations te
        JOIN tasks t ON t.id = te.task_id
        WHERE {PREDICATE}
        GROUP BY t.project_id
        ORDER BY n DESC
    """)).fetchall()
    for project_id, n in rows:
        print(f"  {n:>5}  project={project_id}")
    print()
    print("sample (current value → normalized value), 8 rows:")
    sample = db.execute(text(f"""
        SELECT te.id::text,
               (metrics->'korrektur_falloesung'->>'value') AS cur_value,
               (metrics->'korrektur_falloesung'->'details'->>'raw_score') AS raw_score
        FROM task_evaluations te
        WHERE {PREDICATE}
        LIMIT 8
    """)).fetchall()
    for tid, cur, raw in sample:
        try:
            nv = f"{float(raw) / 100.0:.4f}"
        except (TypeError, ValueError):
            nv = "?"
        print(f"  te={tid}  value {cur} → {nv}  (raw_score {raw} unchanged)")
    return total


def _apply(db) -> int:
    result = db.execute(text(f"""
        UPDATE task_evaluations
        SET metrics = jsonb_set(
            metrics,
            '{{korrektur_falloesung,value}}',
            to_jsonb(
                (metrics->'korrektur_falloesung'->'details'->>'raw_score')::numeric / 100.0
            )
        )
        WHERE {PREDICATE}
    """))
    return result.rowcount or 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True,
                      help="print summary, do not commit (default)")
    mode.add_argument("--apply", action="store_true", help="commit the normalization")
    args = parser.parse_args()
    apply_mode = bool(args.apply)

    db = next(get_db())
    try:
        if not apply_mode:
            print("=== DRY RUN (no changes will be committed) ===")
            _print_dry_run_summary(db)
            return 0

        before = _count(db)
        print(f"before: {before} rows to normalize")
        updated = _apply(db)
        db.commit()
        after = _count(db)
        print(f"updated rows: {updated}")
        print(f"after: {after} rows remaining (expected: 0)")
        if after != 0:
            print("WARNING: rows still match the predicate after apply.")
            return 1
        print("done.")
        return 0
    except Exception as e:  # noqa: BLE001
        db.rollback()
        print(f"ERROR: {e}")
        return 2
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
