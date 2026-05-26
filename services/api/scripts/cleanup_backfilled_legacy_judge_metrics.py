#!/usr/bin/env python3
"""Backfill `details` on legacy `llm_judge_falloesung` task_evaluations.

Issue #113. Migration 036 wrapped bare-float metric values into the
`{value, method, details: {backfilled_legacy: true}}` envelope. For
`llm_judge_falloesung` the bare value was a 0–1 ratio (e.g. 0.88), so the
wrapper's `value` carries 0–1 while the canonical 0–100 score sits at the
top level (`metrics.raw_score`, `metrics.llm_judge_falloesung_response.score`)
and `details.raw_score` is missing. Consumers that follow the Shape A contract
(read `details.raw_score`, fall back to `value`) silently mix 0–100 and 0–1
numbers.

This script surfaces the canonical Shape A fields into `details` by copying
data that already exists on the same row at the top level. It synthesizes
nothing — `raw_output` and `call_metadata` (audit-trail fields the regular
rows carry but were never captured for backfilled rows) remain absent.
`backfilled_legacy: true` stays as a permanent provenance marker so strict
audits can still distinguish "fully captured" from "reconstructed from
companions".

Recovered fields per row:
  * details.raw_score      — from metrics.raw_score
                              (fallback: metrics.llm_judge_falloesung_response.score)
  * details.grade_points   — from metrics.llm_judge_falloesung_grade_points
  * details.passed         — from metrics.llm_judge_falloesung_passed (1.0/0.0 → bool)
  * details.judge_response — copy of metrics.llm_judge_falloesung_response
  * details.recovered_at   — ISO timestamp of this run
  * details.recovered_from — list of source keys actually used

Optional: rewrite `llm_judge_falloesung.value` to `raw_score / 100.0` so the
Shape A wrapper is self-consistent (toggle with --no-rewrite-value).

Idempotent: the predicate excludes rows that already have `details.raw_score`.

Usage (inside the api container):
  python /app/scripts/cleanup_backfilled_legacy_judge_metrics.py --dry-run
  python /app/scripts/cleanup_backfilled_legacy_judge_metrics.py --apply
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from sqlalchemy import text

from database import get_db


PREDICATE = """
    jsonb_typeof(metrics->'llm_judge_falloesung') = 'object'
    AND metrics->'llm_judge_falloesung'->'details'->>'backfilled_legacy' = 'true'
    AND metrics->'llm_judge_falloesung'->'details'->>'raw_score' IS NULL
"""


def _print_dry_run_summary(db) -> int:
    total = db.execute(text(f"SELECT COUNT(*) FROM task_evaluations WHERE {PREDICATE}")).scalar() or 0
    print(f"affected rows: {total}")
    if total == 0:
        return 0

    print()
    print("per (project_id, field_name):")
    rows = db.execute(text("""
        SELECT t.project_id::text AS project_id, te.field_name, COUNT(*) AS n
        FROM task_evaluations te
        JOIN tasks t ON t.id = te.task_id
        WHERE {PREDICATE}
        GROUP BY t.project_id, te.field_name
        ORDER BY n DESC
    """)).fetchall()
    for project_id, field_name, n in rows:
        print(f"  {n:>5}  project={project_id}  field={field_name}")

    print()
    print("recoverability (all should equal affected rows):")
    r = db.execute(text("""
        SELECT
          COUNT(*) FILTER (WHERE metrics->>'raw_score' IS NOT NULL),
          COUNT(*) FILTER (WHERE metrics->'llm_judge_falloesung_response'->>'score' IS NOT NULL),
          COUNT(*) FILTER (WHERE metrics->>'llm_judge_falloesung_passed' IS NOT NULL),
          COUNT(*) FILTER (WHERE metrics->>'llm_judge_falloesung_grade_points' IS NOT NULL),
          COUNT(*) FILTER (
            WHERE metrics->>'raw_score' IS NULL
              AND metrics->'llm_judge_falloesung_response'->>'score' IS NULL
          )
        FROM task_evaluations
        WHERE {PREDICATE}
    """)).fetchone()
    print(f"  has top-level raw_score:       {r[0]}")
    print(f"  has response.score:            {r[1]}")
    print(f"  has _passed:                   {r[2]}")
    print(f"  has _grade_points:             {r[3]}")
    print(f"  UNRECOVERABLE (no score src):  {r[4]}")
    if r[4]:
        print()
        print(f"  warning: {r[4]} rows cannot be recovered (no raw_score and no response.score).")
        print("  these will be skipped on --apply and logged below.")
        skipped = db.execute(text("""
            SELECT te.id::text, t.project_id::text, te.field_name
            FROM task_evaluations te
            JOIN tasks t ON t.id = te.task_id
            WHERE {PREDICATE}
              AND metrics->>'raw_score' IS NULL
              AND metrics->'llm_judge_falloesung_response'->>'score' IS NULL
            ORDER BY t.project_id, te.field_name
            LIMIT 20
        """)).fetchall()
        for tid, pid, fn in skipped:
            print(f"    skip  te={tid}  project={pid}  field={fn}")

    print()
    print("sample of resulting `llm_judge_falloesung.details` (5 rows):")
    sample = db.execute(text("""
        SELECT te.id::text,
               metrics->>'raw_score' AS top_raw,
               metrics->'llm_judge_falloesung'->>'value' AS old_value,
               metrics->'llm_judge_falloesung_response'->>'score' AS resp_score,
               metrics->>'llm_judge_falloesung_passed' AS pass_flag,
               metrics->>'llm_judge_falloesung_grade_points' AS gp
        FROM task_evaluations te
        WHERE {PREDICATE}
        LIMIT 5
    """)).fetchall()
    for tid, raw, oldv, rs, pf, gp in sample:
        print(f"  te={tid}  top_raw={raw}  old_value={oldv}  resp_score={rs}  passed={pf}  grade_points={gp}")
    return total


def _apply(db, rewrite_value: bool) -> tuple[int, int]:
    """Apply the cleanup. Returns (updated, skipped_unrecoverable)."""
    recovered_at = datetime.now(timezone.utc).isoformat()

    # Build the patched details blob in SQL. COALESCE picks raw_score from
    # top-level first, then response.score. Skip rows where both are NULL.
    value_update = (
        "'value', "
        "(COALESCE(metrics->>'raw_score', metrics->'llm_judge_falloesung_response'->>'score')::numeric / 100.0)"
        if rewrite_value
        else "'value', metrics->'llm_judge_falloesung'->'value'"
    )

    update_sql = text("""
        WITH updates AS (
          SELECT
            te.id,
            jsonb_set(
              metrics,
              '{{llm_judge_falloesung}}',
              jsonb_build_object(
                'error', metrics->'llm_judge_falloesung'->'error',
                {value_update},
                'method', metrics->'llm_judge_falloesung'->'method',
                'details', jsonb_build_object(
                  'backfilled_legacy', true,
                  'raw_score',
                    COALESCE(metrics->>'raw_score', metrics->'llm_judge_falloesung_response'->>'score')::numeric,
                  'grade_points',
                    NULLIF(metrics->>'llm_judge_falloesung_grade_points', '')::numeric,
                  'passed',
                    CASE
                      WHEN metrics->>'llm_judge_falloesung_passed' IS NULL THEN NULL
                      WHEN (metrics->>'llm_judge_falloesung_passed')::numeric >= 0.5 THEN true
                      ELSE false
                    END,
                  'judge_response', metrics->'llm_judge_falloesung_response',
                  'recovered_at', :recovered_at,
                  'recovered_from',
                    CASE
                      WHEN metrics->>'raw_score' IS NOT NULL
                        THEN to_jsonb(ARRAY['raw_score','llm_judge_falloesung_response','llm_judge_falloesung_passed','llm_judge_falloesung_grade_points'])
                      ELSE to_jsonb(ARRAY['llm_judge_falloesung_response.score','llm_judge_falloesung_response','llm_judge_falloesung_passed','llm_judge_falloesung_grade_points'])
                    END
                )
              )
            ) AS new_metrics
          FROM task_evaluations te
          WHERE {PREDICATE}
            AND (metrics->>'raw_score' IS NOT NULL
                 OR metrics->'llm_judge_falloesung_response'->>'score' IS NOT NULL)
        )
        UPDATE task_evaluations te
        SET metrics = u.new_metrics
        FROM updates u
        WHERE te.id = u.id
    """)
    result = db.execute(update_sql, {"recovered_at": recovered_at})
    updated = result.rowcount or 0

    skipped = db.execute(text("""
        SELECT COUNT(*) FROM task_evaluations
        WHERE {PREDICATE}
          AND metrics->>'raw_score' IS NULL
          AND metrics->'llm_judge_falloesung_response'->>'score' IS NULL
    """)).scalar() or 0

    return updated, skipped


def _verify_clean(db) -> int:
    return db.execute(text(f"SELECT COUNT(*) FROM task_evaluations WHERE {PREDICATE}")).scalar() or 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True,
                      help="print summary, do not commit (default)")
    mode.add_argument("--apply", action="store_true",
                      help="commit the cleanup update")
    parser.add_argument("--rewrite-value", action=argparse.BooleanOptionalAction, default=True,
                        help="also rewrite llm_judge_falloesung.value to raw_score/100.0 (default: on)")
    args = parser.parse_args()
    apply_mode = bool(args.apply)

    db = next(get_db())
    try:
        if not apply_mode:
            print("=== DRY RUN (no changes will be committed) ===")
            _print_dry_run_summary(db)
            return 0

        before = _verify_clean(db)
        print(f"before: {before} affected rows")
        updated, skipped = _apply(db, rewrite_value=args.rewrite_value)
        db.commit()
        after = _verify_clean(db)
        print(f"updated rows: {updated}")
        print(f"skipped (unrecoverable): {skipped}")
        print(f"after: {after} affected rows (expected: {skipped})")
        if after != skipped:
            print("WARNING: post-apply count does not match expected skipped count.")
            return 1
        print("done.")
        return 0
    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}")
        return 2
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
