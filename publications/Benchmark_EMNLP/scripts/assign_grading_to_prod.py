"""Push pre-computed Benchathon grading assignments into the prod platform.

Designed to be copied into the running benger-api pod and run there with
kubectl exec, so it uses the same DATABASE_URI as the API itself.

Reads:
  - benchathon_human_grading_sample.csv (45 rows; pick_id -> task_id, target_type, target_id)
  - benchathon_human_grading_assignments.csv (180 rows; the planned (user, role, pick) tuples)

Writes:
  - one task_assignments row per planned (user_id, task_id, target_type, target_id)
    with notes 'evaluator_type=<role>;pick_id=<pid>;pass=<pass>;source=<tag>'

Idempotent: re-runs INSERT ... ON CONFLICT DO NOTHING against the partial unique
index uniq_item_level_assignment.

Usage (inside the pod):
    python /tmp/assign_grading_to_prod.py \
        --picks /tmp/benchathon_human_grading_sample.csv \
        --assigns /tmp/benchathon_human_grading_assignments.csv \
        --dry-run --defer-reviewer Martin

Then with --execute instead of --dry-run when ready.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import uuid
from collections import Counter, defaultdict
from typing import Any

from sqlalchemy import create_engine, text


DEFAULT_PROJECT_ID = "e529779b-300f-48c0-89cb-90f3f4b72a51"          # Benchathon
DEFAULT_ASSIGNED_BY = "c137f76b-ac24-4624-a530-b7abd1ed7552"         # Sebastian (superadmin)
DEFAULT_SOURCE_TAG = "arr_dataset_2026-05-11"
DEFAULT_METRIC = "korrektur_falloesung"
DEFAULT_ORG_ID = "94e3b649-812f-4fac-a63d-a0e0228eae9c"              # Benchathon org

ELIGIBLE_ORG_ROLES = ("CONTRIBUTOR", "ORG_ADMIN", "ADMIN")
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)


def info(*msg: Any) -> None:
    print(*msg, flush=True)


def section(title: str) -> None:
    info()
    info("=" * 72)
    info(title)
    info("=" * 72)


def load_csv(path: str) -> list[dict[str, str]]:
    with open(path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build_planned(picks_path: str, assigns_path: str,
                  source_tag: str, deferred_names: set[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (planned_rows, deferred_rows).

    Neither CSV carries the task_id UUID directly — it has to be filled in later
    by looking up annotations/generations on prod. Each row leaves task_id=None
    until backfill_task_ids() runs.
    """
    picks = {p["pick_id"]: p for p in load_csv(picks_path)}
    assigns = load_csv(assigns_path)
    planned: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    for a in assigns:
        pick = picks[a["pick_id"]]
        target_type = "annotation" if pick["subject_type"] == "human" else "generation"
        row = {
            "task_id":      None,  # filled by backfill_task_ids
            "user_id":      a["reviewer_uuid"],
            "target_type":  target_type,
            "target_id":    pick["subject_id"],
            "notes": (
                f"evaluator_type={a['reviewer_role']};"
                f"pick_id={a['pick_id']};"
                f"pass={a['pass']};"
                f"source={source_tag}"
            ),
            "_reviewer_name": a["reviewer_name"],
            "_pick_id":       a["pick_id"],
        }
        if not UUID_RE.match(row["user_id"]):
            deferred.append({**row, "_defer_reason": f"malformed user_id ({row['user_id']!r})"})
            continue
        if a["reviewer_name"] in deferred_names:
            deferred.append({**row, "_defer_reason": "explicit --defer-reviewer"})
            continue
        planned.append(row)
    return planned, deferred


def backfill_task_ids(conn, planned: list[dict[str, Any]], project_id: str) -> bool:
    """Look up task_id for each (target_type, target_id) on prod. Return True on success."""
    ann_ids = sorted({p["target_id"] for p in planned if p["target_type"] == "annotation"})
    gen_ids = sorted({p["target_id"] for p in planned if p["target_type"] == "generation"})
    task_by_target: dict[tuple[str, str], str] = {}
    if ann_ids:
        for r in conn.execute(text(
            "select id, task_id from annotations where id = ANY(:ids) and project_id = :pid"
        ), {"ids": ann_ids, "pid": project_id}):
            task_by_target[("annotation", r.id)] = r.task_id
    if gen_ids:
        for r in conn.execute(text(
            "select g.id, g.task_id from generations g join tasks t on t.id = g.task_id "
            "where g.id = ANY(:ids) and t.project_id = :pid"
        ), {"ids": gen_ids, "pid": project_id}):
            task_by_target[("generation", r.id)] = r.task_id
    missing = []
    for p in planned:
        tid = task_by_target.get((p["target_type"], p["target_id"]))
        if not tid:
            missing.append(p)
        else:
            p["task_id"] = tid
    if missing:
        info(f"  ✗ {len(missing)} planned rows have no matching annotation/generation on prod:")
        for m in missing[:5]:
            info(f"    {m['_pick_id']} {m['target_type']}/{m['target_id'][:8]}")
        return False
    return True


def preflight(conn, project_id: str, org_id: str, metric: str,
              planned: list[dict[str, Any]]) -> bool:
    """Return True iff every check passes. Prints findings either way."""
    ok = True

    # a) project korrektur_enabled & has metric
    r = conn.execute(text(
        "select korrektur_enabled, evaluation_config from projects where id = :pid"
    ), {"pid": project_id}).first()
    if not r:
        info(f"  ✗ project {project_id} not found"); return False
    info(f"  ✓ project found; korrektur_enabled={r.korrektur_enabled}")
    if not r.korrektur_enabled:
        info("  ✗ korrektur not enabled"); ok = False
    ec = r.evaluation_config or {}
    metrics = {e.get("metric"): e.get("enabled") for e in (ec.get("evaluation_configs") or [])}
    if metrics.get(metric) is not True:
        info(f"  ✗ metric {metric!r} not enabled (state: {metrics.get(metric)})"); ok = False
    else:
        info(f"  ✓ metric {metric!r} enabled")

    # c) user eligibility
    user_ids = sorted({p["user_id"] for p in planned})
    if not user_ids:
        info("  (no planned users to check)")
    else:
        rows = conn.execute(text(
            "select u.id, u.name from users u where u.id = ANY(:uids)"
        ), {"uids": user_ids}).all()
        found = {r.id for r in rows}
        missing = [u for u in user_ids if u not in found]
        if missing:
            info(f"  ✗ users not found: {missing}"); ok = False
        else:
            info(f"  ✓ all {len(user_ids)} planned users exist")
        memb_rows = conn.execute(text(
            "select user_id, role from organization_memberships "
            "where organization_id = :oid and user_id = ANY(:uids) and is_active = true"
        ), {"oid": org_id, "uids": user_ids}).all()
        role_by_uid = {r.user_id: r.role for r in memb_rows}
        ineligible = [u for u in user_ids if role_by_uid.get(u) not in ELIGIBLE_ORG_ROLES]
        if ineligible:
            info(f"  ✗ users not eligible (need role in {ELIGIBLE_ORG_ROLES}):")
            for u in ineligible:
                info(f"      {u} role={role_by_uid.get(u)!r}")
            ok = False
        else:
            info(f"  ✓ all {len(user_ids)} users eligible (CONTRIBUTOR+/ORG_ADMIN in Benchathon org)")

    # d) target_ids exist
    ann_ids = sorted({p["target_id"] for p in planned if p["target_type"] == "annotation"})
    gen_ids = sorted({p["target_id"] for p in planned if p["target_type"] == "generation"})
    if ann_ids:
        n = conn.execute(text(
            "select count(*) from annotations where id = ANY(:ids) and project_id = :pid"
        ), {"ids": ann_ids, "pid": project_id}).scalar()
        if n != len(ann_ids):
            info(f"  ✗ annotations: {n}/{len(ann_ids)} found on this project"); ok = False
        else:
            info(f"  ✓ all {len(ann_ids)} annotation target_ids exist on project")
    if gen_ids:
        n = conn.execute(text(
            "select count(*) from generations g join tasks t on t.id = g.task_id "
            "where g.id = ANY(:ids) and t.project_id = :pid"
        ), {"ids": gen_ids, "pid": project_id}).scalar()
        if n != len(gen_ids):
            info(f"  ✗ generations: {n}/{len(gen_ids)} found on this project"); ok = False
        else:
            info(f"  ✓ all {len(gen_ids)} generation target_ids exist on project")

    # e) backfill task_id for each planned row (from target lookup), then count
    if planned:
        if not backfill_task_ids(conn, planned, project_id):
            ok = False
        else:
            task_ids = sorted({p["task_id"] for p in planned})
            info(f"  ✓ resolved {len(planned)} target_ids → {len(task_ids)} distinct task_ids")

    return ok


def summarize(planned: list[dict[str, Any]], deferred: list[dict[str, Any]]) -> None:
    info(f"  planned:  {len(planned)}")
    info(f"  deferred: {len(deferred)}")
    info("  planned per reviewer (CSV name → effective user_id):")
    per_rev: dict[tuple[str, str, bool], int] = defaultdict(int)
    for p in planned:
        per_rev[(p["_reviewer_name"], p["user_id"], "_reassigned_from" in p)] += 1
    for (name, uid, reassigned), n in sorted(per_rev.items()):
        suffix = f"  ← reassigned (test cohort, uid={uid[:8]}…)" if reassigned else ""
        info(f"    {name:<14} {n}{suffix}")
    if deferred:
        info("  deferred per reviewer:")
        per_def = defaultdict(Counter)
        for d in deferred:
            per_def[d["_reviewer_name"]][d["_defer_reason"]] += 1
        for name, reasons in per_def.items():
            for reason, n in reasons.items():
                info(f"    {name:<14} {n}  ({reason})")
    roles = Counter()
    for p in planned:
        # notes starts with 'evaluator_type=...;...'
        role = p["notes"].split(";", 1)[0].split("=", 1)[1]
        roles[role] += 1
    info(f"  planned by role: {dict(roles)}")


def execute_inserts(conn, planned: list[dict[str, Any]], project_id: str,
                    assigned_by: str) -> tuple[int, int]:
    """Run the INSERTs in a single transaction. Return (inserted, skipped)."""
    inserted = 0
    skipped = 0
    # Note the WHERE clause: the matching unique index is partial
    # (uniq_item_level_assignment, WHERE target_type <> 'task'), so Postgres
    # requires the predicate in the ON CONFLICT inference for it to match.
    sql = text("""
        INSERT INTO task_assignments
            (id, task_id, user_id, assigned_by, status, priority, notes,
             assigned_at, target_type, target_id)
        VALUES
            (:id, :task_id, :user_id, :assigned_by, 'assigned', 0, :notes,
             now(), :target_type, :target_id)
        ON CONFLICT (task_id, user_id, target_type, target_id) WHERE target_type <> 'task'
        DO NOTHING
        RETURNING id
    """)
    for p in planned:
        row_id = str(uuid.uuid4())
        result = conn.execute(sql, {
            "id":           row_id,
            "task_id":      p["task_id"],
            "user_id":      p["user_id"],
            "assigned_by":  assigned_by,
            "notes":        p["notes"],
            "target_type":  p["target_type"],
            "target_id":    p["target_id"],
        })
        rows = result.fetchall()
        if rows:
            inserted += 1
        else:
            skipped += 1
    return inserted, skipped


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--picks", required=True)
    ap.add_argument("--assigns", required=True)
    ap.add_argument("--project-id", default=DEFAULT_PROJECT_ID)
    ap.add_argument("--assigned-by", default=DEFAULT_ASSIGNED_BY)
    ap.add_argument("--source-tag", default=DEFAULT_SOURCE_TAG)
    ap.add_argument("--metric", default=DEFAULT_METRIC)
    ap.add_argument("--org-id", default=DEFAULT_ORG_ID)
    ap.add_argument("--defer-reviewer", action="append", default=[])
    ap.add_argument("--reassign-deferred-to", default=None,
                    help="UUID. When set, all deferred rows are re-targeted to "
                         "this user_id (and given a distinct source tag) so they "
                         "can be inserted as a test cohort. Used to drive UI checks "
                         "while the real reviewer's account isn't ready yet.")
    ap.add_argument("--reassign-source-tag", default=None,
                    help="Source tag for the re-targeted rows (must differ from "
                         "--source-tag so the test cohort can be rolled back "
                         "independently). Required if --reassign-deferred-to is set.")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    deferred_names = set(args.defer_reviewer)
    if args.reassign_deferred_to and not args.reassign_source_tag:
        info("✗ --reassign-deferred-to requires --reassign-source-tag (must differ "
             "from --source-tag so the test cohort is rollback-isolated)")
        return 2
    if args.reassign_source_tag and args.reassign_source_tag == args.source_tag:
        info("✗ --reassign-source-tag must differ from --source-tag")
        return 2

    section(f"Loading {args.picks} + {args.assigns}")
    planned, deferred = build_planned(args.picks, args.assigns, args.source_tag, deferred_names)
    info(f"  parsed {len(planned) + len(deferred)} total assignments")

    # Re-target deferred rows to the test user when requested. Each row gets the
    # new user_id and a notes string tagged with the alternate source so a single
    # DELETE WHERE notes LIKE '%source=<test_tag>%' can roll back the test cohort
    # without disturbing the 165 production rows.
    if args.reassign_deferred_to:
        if not UUID_RE.match(args.reassign_deferred_to):
            info(f"✗ --reassign-deferred-to is not a valid UUID: {args.reassign_deferred_to!r}")
            return 2
        retargeted = []
        for d in deferred:
            new_notes = d["notes"].replace(
                f"source={args.source_tag}",
                f"source={args.reassign_source_tag}",
            )
            retargeted.append({**d,
                               "user_id": args.reassign_deferred_to,
                               "notes":   new_notes,
                               "_reassigned_from": d["_reviewer_name"]})
        info(f"  re-targeted {len(retargeted)} deferred rows to {args.reassign_deferred_to} "
             f"with source={args.reassign_source_tag}")
        planned.extend(retargeted)
        deferred = []

    section("Planned vs deferred summary")
    summarize(planned, deferred)

    db_url = os.environ.get("DATABASE_URI")
    if not db_url:
        info("✗ DATABASE_URI not set. This script must run inside the api pod.")
        return 2

    engine = create_engine(db_url)
    with engine.connect() as conn:
        section("Pre-flight checks")
        if not preflight(conn, args.project_id, args.org_id, args.metric, planned):
            info("\n  ✗ pre-flight failed; aborting")
            return 1
        info("\n  ✓ all pre-flight checks passed")

        if args.dry_run:
            section("Dry-run — first 5 planned INSERTs")
            for p in planned[:5]:
                info(f"  {p['_pick_id']}  user={p['_reviewer_name']:<12} task={p['task_id'][:8]} "
                     f"target={p['target_type']}/{p['target_id'][:8]}  notes={p['notes']}")
            info("\n  ✓ dry-run complete; no rows written")
            return 0

        # execute
        section("Executing INSERTs")
        try:
            ins, skp = execute_inserts(conn, planned, args.project_id, args.assigned_by)
            conn.commit()
        except Exception as e:
            conn.rollback()
            info(f"  ✗ transaction rolled back: {e}")
            return 1
        info(f"  ✓ inserted={ins}  skipped(duplicate)={skp}  deferred={len(deferred)}  planned_total={len(planned)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
