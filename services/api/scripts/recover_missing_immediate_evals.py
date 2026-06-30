#!/usr/bin/env python3
"""Recover LOST immediate-eval votes (KI-Votum) — additive, never overwrites.

Immediate evaluation is fired CLIENT-side: the labeling page POSTs
``/immediate`` after a successful annotation submit, then polls. There is no
server-side fallback (``on_annotation_created`` only closes the timer + clears
drafts). So if that POST never lands — tab closed right after submit, transient
network blip — the annotation gets NO vote and nothing ever retries it. (This
is exactly what happened to one Göttingen exam submission on 2026-06-17.)

This tool finds those orphans and re-dispatches the SAME immediate-eval task
the endpoint would (``tasks.run_single_sample_evaluation``), so the missing
vote gets produced.

SAFETY (the hard constraint): this script is strictly ADDITIVE.
  * It only targets annotations that have ZERO existing immediate-eligible
    ``TaskEvaluation`` rows (a real score for ANY eligible metric counts as
    "has a vote" → skipped). It never re-grades an annotation that already
    carries a vote, so no existing grade can be overwritten or duplicated.
  * Partially-graded annotations (some eligible metrics present, some missing)
    are REPORTED but never acted on — re-dispatching them risks a duplicate for
    the already-present metric. Handle those by hand if they ever appear.
  * It only INSERTs a new ``EvaluationRun`` + dispatches a task. It issues no
    UPDATE/DELETE against ``task_evaluations`` or ``evaluation_runs``.
  * ``--min-age-minutes`` (default 15) skips very recent submits so an
    in-flight client eval isn't raced into a duplicate.

Scope: projects with ``immediate_evaluation_enabled`` AND at least one enabled
immediate-eligible config. Use ``--project-id`` for one project or ``--all``.

Usage (inside the api container):
  python /app/scripts/recover_missing_immediate_evals.py --project-id <id>            # dry-run
  python /app/scripts/recover_missing_immediate_evals.py --project-id <id> --apply
  python /app/scripts/recover_missing_immediate_evals.py --all                        # dry-run, all projects
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (
    "/shared",
    "/app",
    os.path.dirname(_HERE),
    os.path.join(os.path.dirname(os.path.dirname(_HERE)), "shared"),
):
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

import models  # noqa: E402,F401
import project_models  # noqa: E402,F401
from database import SessionLocal  # noqa: E402
from immediate_eval_dispatch import (  # noqa: E402
    eligible_configs as _eligible_configs,
    eligible_metrics as _eligible_metrics,
    ensure_immediate_evaluation,
    scan_ungraded,
)
from models import User  # noqa: E402
from project_models import Project  # noqa: E402

try:
    from celery_client import send_task_safe
except Exception:  # pragma: no cover - only needed for --apply
    send_task_safe = None


def _scan_project(db, project, cutoff):
    """Return (candidates, partials, eligible) for one project.

    Thin wrapper over the shared ``scan_ungraded`` so the CLI and the hourly
    sweep agree on what "ungraded" means.
    """
    eligible = _eligible_configs(project)
    if not eligible:
        return [], [], eligible
    candidates, partials = scan_ungraded(db, project, cutoff=cutoff)
    return candidates, partials, eligible


def _dispatch(db, project, eligible, annotation, task, apply: bool) -> str:
    """Delegate to the shared, idempotent ``ensure_immediate_evaluation`` so the
    CLI and every live trigger share one code path. Returns the run id."""
    if not apply:
        return str(uuid.uuid4())
    rid = ensure_immediate_evaluation(
        db,
        project,
        task,
        annotation,
        configs=eligible,
        trigger="recover_missing_immediate_evals",
    )
    return rid or str(uuid.uuid4())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--project-id", help="recover one project")
    scope.add_argument("--all", action="store_true",
                       help="recover all immediate-eval-enabled projects")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True,
                      help="report only, dispatch nothing (default)")
    mode.add_argument("--apply", action="store_true", help="dispatch recoveries")
    parser.add_argument("--min-age-minutes", type=int, default=15,
                        help="skip submits newer than this (avoid racing in-flight "
                             "client evals); default 15")
    args = parser.parse_args()
    apply_mode = bool(args.apply)
    if apply_mode and send_task_safe is None:
        print("ERROR: celery_client.send_task_safe unavailable; cannot --apply.")
        return 2

    # NOTE: new()/utcnow() are fine here — this is a CLI one-shot, not a workflow.
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=args.min_age_minutes)

    db = SessionLocal()
    try:
        q = db.query(Project).filter(Project.immediate_evaluation_enabled == True)  # noqa: E712
        if args.project_id:
            q = q.filter(Project.id == args.project_id)
        projects = q.all()

        if not apply_mode:
            print("=== DRY RUN (nothing dispatched) ===")
        print(f"scanning {len(projects)} immediate-eval project(s); "
              f"min-age={args.min_age_minutes}m (cutoff {cutoff.isoformat()})\n")

        total_candidates = total_dispatched = total_partials = 0
        for p in projects:
            candidates, partials, eligible = _scan_project(db, p, cutoff)
            if not eligible:
                continue
            if not candidates and not partials:
                continue
            print(f"PROJECT {str(p.id)[:8]}  {p.title!r}")
            print(f"   eligible metrics: {sorted(_eligible_metrics(eligible))}")
            print(f"   missing-vote annotations: {len(candidates)}  "
                  f"partial (reported only): {len(partials)}")
            for a, task in candidates:
                u = db.query(User).filter(User.id == a.completed_by).first()
                uname = u.username if u else str(a.completed_by)[:8]
                rid = _dispatch(db, p, eligible, a, task, apply_mode)
                verb = "DISPATCHED" if apply_mode else "would dispatch"
                print(f"      {verb}  ann={a.id}  user={uname}  submitted={a.created_at}  run={rid}")
                total_candidates += 1
                total_dispatched += 1 if apply_mode else 0
            for a, present, missing in partials:
                print(f"      PARTIAL (skipped) ann={a.id}  present={sorted(present)}  "
                      f"missing={sorted(missing)}")
                total_partials += 1
            print()

        print(f"missing-vote annotations: {total_candidates}")
        print(f"partial annotations (skipped, manual review): {total_partials}")
        if apply_mode:
            print(f"dispatched: {total_dispatched}")
        else:
            print("dry-run: nothing dispatched. Re-run with --apply to recover.")
        return 0
    except Exception as e:  # noqa: BLE001
        db.rollback()
        print(f"ERROR: {e}")
        return 2
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
