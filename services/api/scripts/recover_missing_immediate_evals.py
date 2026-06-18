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
from metric_filters import is_immediate_eligible  # noqa: E402
from models import EvaluationRun, OrganizationMembership, TaskEvaluation, User  # noqa: E402
from project_models import Annotation, Project, Task  # noqa: E402

try:
    from celery_client import send_task_safe
except Exception:  # pragma: no cover - only needed for --apply
    send_task_safe = None


def _eligible_configs(project) -> list[dict]:
    cfg = project.evaluation_config or {}
    configs = cfg.get("evaluation_configs") or cfg.get("multi_field_evaluations") or []
    return [
        c
        for c in configs
        if c.get("enabled", True) and is_immediate_eligible(c.get("metric", ""))
    ]


def _eligible_metrics(eligible_configs) -> set:
    return {c.get("metric", "") for c in eligible_configs}


def _row_has_real_score_for(metrics, eligible_metrics: set) -> bool:
    """True if the row carries a non-error score for any eligible metric."""
    if not isinstance(metrics, dict):
        return False
    for m in eligible_metrics:
        if m not in metrics:
            continue
        v = metrics[m]
        if isinstance(v, dict):
            if v.get("error"):
                continue
            if v.get("value") is not None:
                return True
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            return True
    return False


def _parse_annotation_results(annotation) -> dict:
    """Replicate the immediate-eval endpoint's annotation.result -> dict parse
    (keyed by ``from_name``). Generic Label-Studio shape handling."""
    out: dict = {}
    res = annotation.result
    if not (res and isinstance(res, list)):
        return out
    for region in res:
        if not isinstance(region, dict):
            continue
        from_name = region.get("from_name")
        if not from_name:
            continue
        value = region.get("value", {})
        region_type = region.get("type", "")
        if isinstance(value, str):
            out[from_name] = value
            continue
        if isinstance(value, dict) and "markdown" in value:
            out[from_name] = value["markdown"]
            continue
        if region_type == "textarea":
            texts = value.get("text", [])
            out[from_name] = "\n".join(texts) if isinstance(texts, list) else str(texts)
        elif region_type == "choices":
            choices = value.get("choices", [])
            out[from_name] = choices[0] if len(choices) == 1 else choices
        elif region_type == "rating":
            out[from_name] = value.get("rating")
        elif "text" in value:
            texts = value["text"]
            out[from_name] = "\n".join(texts) if isinstance(texts, list) else str(texts)
        else:
            for v in value.values():
                if v:
                    out[from_name] = v if isinstance(v, str) else str(v)
                    break
    return out


def _resolve_org(db, project, user_id):
    """Mirror routers.evaluations.helpers.resolve_user_org_for_project without
    importing the router module."""
    if not project.organizations:
        return None
    org_ids = {str(o.id) for o in project.organizations}
    m = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.is_active == True,  # noqa: E712
            OrganizationMembership.organization_id.in_(org_ids),
        )
        .first()
    )
    if m:
        return str(m.organization_id)
    return str(project.organizations[0].id)


def _scan_project(db, project, cutoff):
    """Return (candidates, partials) for one project.

    candidate = (annotation, task) with ZERO eligible real-score rows.
    partial   = (annotation, present_metrics, missing_metrics) — reported only.
    """
    eligible = _eligible_configs(project)
    if not eligible:
        return [], [], eligible
    elig_metrics = _eligible_metrics(eligible)

    anns = (
        db.query(Annotation)
        .filter(
            Annotation.project_id == project.id,
            Annotation.was_cancelled == False,  # noqa: E712
            Annotation.result.isnot(None),
            Annotation.created_at < cutoff,
        )
        .all()
    )
    if not anns:
        return [], [], eligible

    tasks_by_id = {
        t.id: t
        for t in db.query(Task).filter(Task.id.in_({a.task_id for a in anns})).all()
    }

    candidates, partials = [], []
    for a in anns:
        rows = (
            db.query(TaskEvaluation.metrics)
            .filter(TaskEvaluation.annotation_id == a.id)
            .all()
        )
        present = set()
        for (m,) in rows:
            if _row_has_real_score_for(m, elig_metrics):
                if isinstance(m, dict):
                    present |= {k for k in m.keys() if k in elig_metrics}
        if not present:
            task = tasks_by_id.get(a.task_id)
            if task is not None:
                candidates.append((a, task))
        elif present < elig_metrics:
            partials.append((a, present, elig_metrics - present))
    return candidates, partials, eligible


def _dispatch(db, project, eligible, annotation, task, apply: bool) -> str:
    """Pre-create the immediate EvaluationRun + dispatch the worker task — the
    exact shape the endpoint uses. Returns the new eval_record_id."""
    eval_record_id = str(uuid.uuid4())
    if not apply:
        return eval_record_id
    annotation_results = _parse_annotation_results(annotation)
    org = _resolve_org(db, project, annotation.completed_by)
    meta = {
        "evaluation_type": "immediate",
        "trigger": "recover_missing_immediate_evals",
        "expected_config_count": len(eligible),
        "configs": [
            {
                "id": c.get("id", c.get("metric", "")),
                "metric": c.get("metric", ""),
                "display_name": c.get("display_name", c.get("metric", "")),
            }
            for c in eligible
        ],
    }
    db.add(
        EvaluationRun(
            id=eval_record_id,
            project_id=str(project.id),
            model_id="immediate",
            evaluation_type_ids=[c.get("metric", "") for c in eligible],
            status="running",
            created_by=str(annotation.completed_by),
            eval_metadata=meta,
            metrics={},
        )
    )
    db.commit()
    send_task_safe(
        "tasks.run_single_sample_evaluation",
        kwargs={
            "evaluation_record_id": eval_record_id,
            "project_id": str(project.id),
            "task_id": str(task.id),
            "annotation_id": str(annotation.id),
            "evaluation_configs": [dict(c) for c in eligible],
            "annotation_results": annotation_results,
            "task_data": task.data or {},
            "organization_id": org,
            "user_id": str(annotation.completed_by),
        },
        queue="celery",
    )
    return eval_record_id


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
