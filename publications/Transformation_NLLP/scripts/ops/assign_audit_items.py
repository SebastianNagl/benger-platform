#!/usr/bin/env python3
"""Assign Bewertungsbogen-Audit items to graders (per creator→exam mapping).

Reads a mapping file (JSON) of the form

    {
      "project_id": "<audit project id>",
      "assignments": {
        "grader@example.com": [1, 2, 3],       // exam numbers (1-based,
        "other@example.com": [4, 5, 6, 1]      // sorted-KEY.json order —
      }                                        // same order as exam_NN.md)
    }

and, for every exam number, assigns ALL of that exam's annotation items to
the grader via the per-item endpoint (bulk-assign has no per-task scope at
HEAD). Exams listed for two graders (IRR overlap) get both assigned.
Graders must already be org CONTRIBUTORs (or project members) — the
endpoint validates eligibility.

Usage:
  uv run python scripts/ops/assign_audit_items.py \
      --base-url http://api.localhost --mapping data/interim/audit/assignments.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(HERE / "scripts" / "ops"))

from setup_audit_project import Client  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--mapping", required=True)
    parser.add_argument("--admin-email", default=os.environ.get("BENGER_ADMIN_EMAIL", "admin@example.com"))
    parser.add_argument("--admin-password", default=os.environ.get("BENGER_ADMIN_PASSWORD", "admin"))
    parser.add_argument("--dry-run", action="store_true", help="Print the plan, assign nothing")
    args = parser.parse_args()

    mapping = json.loads(Path(args.mapping).read_text(encoding="utf-8"))
    project_id = mapping["project_id"]

    admin = Client(args.base_url)
    admin.login(args.admin_email, args.admin_password)

    # Resolve grader emails -> user ids via the org-agnostic users listing
    # is superadmin-only; simpler: the annotations listing endpoint isn't
    # needed — use /api/users search? Keep it simple: the mapping may carry
    # ids directly ("user:<id>"), else we look the email up via
    # /api/users?search= (superadmin).
    def resolve_user(who: str) -> str:
        if who.startswith("user:"):
            return who.split(":", 1)[1]
        found = admin.request("GET", f"/api/users?search={who}&limit=5")
        users = found.get("users") or found.get("items") or found
        for u in users if isinstance(users, list) else []:
            if u.get("email") == who:
                return u["id"]
        raise SystemExit(f"user not found: {who}")

    # Exam number -> task id, via inner_id order (import preserved
    # audit-task-NN ordering as inner_id NN).
    tasks = admin.request("GET", f"/api/projects/{project_id}/korrektur/pending?page_size=100")
    by_number = {}
    for row in tasks.get("items", []):
        task = row["task"]
        by_number[int(task["inner_id"])] = task["id"]

    # All annotation items per task, from the queue.
    items = []
    page = 1
    while True:
        resp = admin.request(
            "GET",
            f"/api/projects/{project_id}/korrektur/items"
            f"?metric=korrektur_custom&page={page}&page_size=100&filter=all",
        )
        items.extend(resp.get("items", []))
        if len(resp.get("items", [])) < 100:
            break
        page += 1
    items_by_task = {}
    for item in items:
        items_by_task.setdefault(item["task_id"], []).append(item)

    total = 0
    for who, exam_numbers in mapping["assignments"].items():
        uid = resolve_user(who)
        for n in exam_numbers:
            task_id = by_number.get(int(n))
            if not task_id:
                raise SystemExit(f"exam number {n} not found (have {sorted(by_number)})")
            for item in items_by_task.get(task_id, []):
                total += 1
                if args.dry_run:
                    continue
                admin.request(
                    "POST",
                    f"/api/projects/{project_id}/korrektur/items/"
                    f"{item['target_type']}/{item['target_id']}/assign",
                    {"metric": "korrektur_custom", "user_ids": [uid]},
                )
        print(f"{who}: exams {exam_numbers} assigned")
    print(f"{'planned' if args.dry_run else 'created'} {total} item assignments")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
