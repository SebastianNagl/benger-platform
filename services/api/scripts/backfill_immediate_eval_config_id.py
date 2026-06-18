#!/usr/bin/env python3
"""Backfill `evaluation_config_id` on legacy immediate-eval task_evaluations.

Immediate eval persists a BARE ``field_name`` (e.g. ``"human:loesung"``, the
config's prediction field) and — since Issue #111 / migration 057 — also the
discrete ``evaluation_config_id`` column. The batch missing-only matcher
(`workers/tasks.py::run_evaluation`) recognizes bare-field_name immediate rows
as "already done" *via* that column. Rows written before #111 carry
``evaluation_config_id = NULL`` and a bare field_name, so the matcher can't see
them and would re-grade those annotations on the next missing-only run (wasted
LLM budget + parallel/duplicate grades).

This backfills the column on those legacy rows by mapping each row's metric +
bare prediction field to the project's *current* evaluation config carrying that
metric. Only rows with an UNAMBIGUOUS single match are touched; rows that match
zero or multiple configs are skipped and logged — we never guess. This also
satisfies the Issue #111 goal of a discretely-populated config-id for clean
downstream aggregation.

Scope (the candidate predicate):
  * row's EvaluationRun has ``model_id = 'immediate'`` (the immediate lane)
  * ``evaluation_config_id IS NULL``
  * ``field_name`` is bare (contains no ``'|'`` — 3-part rows already carry/derive
    the id and are handled by ``_normalize_field_key``)

Idempotent: assigned rows drop out of the predicate, so re-running finds fewer
(eventually zero) candidates.

Usage (inside the api container):
  python /app/scripts/backfill_immediate_eval_config_id.py --dry-run   # default
  python /app/scripts/backfill_immediate_eval_config_id.py --apply
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter, defaultdict

# Make the api source (database.py) and /shared (models) importable whether run
# from /app in the container or from the repo locally.
_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (
    "/shared",
    "/app",
    os.path.dirname(_HERE),  # services/api when run from the repo
    os.path.join(os.path.dirname(os.path.dirname(_HERE)), "shared"),  # services/shared
):
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

import models  # noqa: E402,F401  — register User/Notification/... before relationships
import project_models  # noqa: E402,F401
from database import SessionLocal  # noqa: E402
from models import EvaluationRun, TaskEvaluation  # noqa: E402
from project_models import Task  # noqa: E402

_WILDCARDS = ("__all_human__", "__all_model__")


def _strip_role(s: str) -> str:
    if s in _WILDCARDS:
        return s
    if s.startswith("human:") or s.startswith("model:"):
        return s.split(":", 1)[1]
    return s


def _field_matches(field_name: str | None, pred_field: str) -> bool:
    """Bare field_name vs a config prediction field, tolerating the
    human:/model: role prefix. Mirrors workers/tasks.py::_pred_field_matches."""
    if not field_name or "|" in field_name:
        return False
    if pred_field in _WILDCARDS:
        return False
    return field_name == pred_field or _strip_role(field_name) == _strip_role(pred_field)


def _project_configs(project) -> list[dict]:
    cfg = project.evaluation_config or {}
    return cfg.get("evaluation_configs") or cfg.get("multi_field_evaluations") or []


def resolve_config_id(metrics, field_name: str | None, configs: list[dict]):
    """Return (config_id, reason). reason ∈ {ok, no_metric, no_field, ambiguous}.

    Match a row to exactly one config by (metric present in the row) AND (the
    config has a prediction field matching the bare field_name).
    """
    if not isinstance(metrics, dict):
        return None, "no_metric"
    config_metrics = {c.get("metric") for c in configs}
    row_metrics = set(metrics.keys()) & config_metrics
    if not row_metrics:
        return None, "no_metric"
    match_ids = set()
    for c in configs:
        if c.get("metric") not in row_metrics:
            continue
        if any(_field_matches(field_name, pf) for pf in c.get("prediction_fields", [])):
            match_ids.add(c.get("id"))
    match_ids.discard(None)
    if len(match_ids) == 1:
        return next(iter(match_ids)), "ok"
    if not match_ids:
        return None, "no_field"
    return None, "ambiguous"


def _candidates(db):
    return (
        db.query(TaskEvaluation)
        .join(EvaluationRun, TaskEvaluation.evaluation_id == EvaluationRun.id)
        .filter(
            EvaluationRun.model_id == "immediate",
            TaskEvaluation.evaluation_config_id.is_(None),
            TaskEvaluation.field_name.isnot(None),
            ~TaskEvaluation.field_name.like("%|%"),
        )
        .all()
    )


def _plan(db):
    """Compute the (row -> config_id) assignment plan + skip reasons."""
    rows = _candidates(db)
    # project_id per task, configs per project (one query each).
    task_ids = {r.task_id for r in rows if r.task_id}
    project_by_task = dict(
        db.query(Task.id, Task.project_id).filter(Task.id.in_(task_ids)).all()
    ) if task_ids else {}
    project_ids = set(project_by_task.values())
    projects = (
        {p.id: p for p in db.query(project_models.Project).filter(project_models.Project.id.in_(project_ids)).all()}
        if project_ids
        else {}
    )

    assign = []  # (row, project_id, config_id)
    skips = []   # (row, project_id, reason)
    for r in rows:
        pid = project_by_task.get(r.task_id)
        project = projects.get(pid)
        if project is None:
            skips.append((r, pid, "no_project"))
            continue
        cid, reason = resolve_config_id(r.metrics, r.field_name, _project_configs(project))
        if reason == "ok":
            assign.append((r, pid, cid))
        else:
            skips.append((r, pid, reason))
    return rows, assign, skips


def _print_summary(rows, assign, skips):
    print(f"candidates (immediate, NULL config-id, bare field_name): {len(rows)}")
    print(f"  resolvable (unambiguous single match): {len(assign)}")
    print(f"  skipped:                               {len(skips)}")
    if assign:
        print("\nassignments per (project_id, config_id, field_name):")
        by = Counter((pid, cid, r.field_name) for r, pid, cid in assign)
        for (pid, cid, fn), n in sorted(by.items(), key=lambda kv: -kv[1]):
            print(f"  {n:>5}  project={pid}  -> config={cid}  field={fn}")
    if skips:
        print("\nskips per reason:")
        by_reason = Counter(reason for _, _, reason in skips)
        for reason, n in by_reason.most_common():
            print(f"  {n:>5}  {reason}")
        print("\nskipped rows (up to 30):")
        for r, pid, reason in skips[:30]:
            mkeys = sorted((r.metrics or {}).keys()) if isinstance(r.metrics, dict) else r.metrics
            print(f"  te={r.id}  project={pid}  field={r.field_name}  reason={reason}  metric_keys={mkeys}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True,
                      help="print the plan, do not commit (default)")
    mode.add_argument("--apply", action="store_true",
                      help="commit the backfill")
    args = parser.parse_args()
    apply_mode = bool(args.apply)

    db = SessionLocal()
    try:
        rows, assign, skips = _plan(db)
        if not apply_mode:
            print("=== DRY RUN (no changes will be committed) ===")
            _print_summary(rows, assign, skips)
            return 0

        _print_summary(rows, assign, skips)
        for r, _pid, cid in assign:
            r.evaluation_config_id = cid
        db.commit()
        print(f"\napplied: set evaluation_config_id on {len(assign)} rows.")
        # Re-check idempotency.
        remaining = len(_candidates(db))
        print(f"remaining candidates after apply: {remaining} (expected: {len(skips)})")
        if remaining != len(skips):
            print("WARNING: remaining candidate count does not match expected skip count.")
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
