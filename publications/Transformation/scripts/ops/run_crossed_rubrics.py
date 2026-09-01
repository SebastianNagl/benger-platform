#!/usr/bin/env python3
"""Crossed rubric-source × judge runs (RQ4 proper / generator outcome ranking).

For every exam in the clone, grade the exam's picks under EVERY contract-valid
v3 rubric that is not the D6-active one (the active rubric's judgments exist
from the main + luna arms), using the '-cross' config (Luna ×3 + Sonnet ×1).

CRITICAL ORDERING: cells resolve the task's ACTIVE rubric at evaluation time,
so within one exam each round must be
    activate rubric -> dispatch run -> wait terminal -> verify rubric_id
before the next rubric activates. Exams are independent and run in parallel
threads. After an exam's last round, its D6 rubric is re-activated and
verified, restoring the clone's original state.

Every completed run is verified: all its rows must carry the intended
details.rubric_id, else the driver aborts that exam loudly.

Output: data/interim/crossed_run_log.jsonl
        one line per (exam, rubric) run: evaluation_id, rubric_id,
        generator_model_id, status, n_rows, verified.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
INTERIM = HERE / "data" / "interim"
LOG = INTERIM / "crossed_run_log.jsonl"
CLONE = "81e474b8-d226-4bf8-bc2e-fb744d25cba5"
CROSS_CONFIG = "llm_judge_rubric-msc0vokl-mmdi-cross"

sys.path.insert(0, str(HERE / "scripts" / "ops"))
from setup_audit_project import Client  # noqa: E402

log_lock = threading.Lock()
print_lock = threading.Lock()


def say(msg):
    with print_lock:
        print(msg, flush=True)


def qsql(sql: str) -> str:
    return subprocess.run(
        ["docker", "exec", "benger-db-1", "psql", "-U", "postgres", "-d", "benger", "-tAc", sql],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def exam_worker(client: Client, task_id: str, spec: dict, rubrics: list, active_id: str,
                cross_cfg: dict, dry: bool, results: list):
    prefix = task_id[:8]
    try:
        for i, rub in enumerate(rubrics, 1):
            say(f"[{prefix}] round {i}/{len(rubrics)}: {rub['generator_model_id']} ({rub['id'][:8]})")
            if dry:
                continue
            client.request(
                "PATCH", f"/api/projects/{CLONE}/bewertungsbogen/{rub['id']}",
                {"action": "activate"},
            )
            body = {
                "project_id": CLONE,
                "evaluation_configs": [cross_cfg],
                "force_rerun": True,
                "task_ids": [task_id],
                "model_ids": spec["model_ids"] or None,
                "annotator_user_ids": spec["annotator_ids"] or None,
            }
            resp = client.request("POST", "/api/evaluations/run", body)
            eval_id = resp["evaluation_id"]
            # Wait for terminal state.
            status = "running"
            for _ in range(240):  # 240 * 15s = 1h cap per round
                time.sleep(15)
                status = qsql(
                    f"select status from evaluation_runs where id='{eval_id}';"
                ) or "missing"
                if status in ("completed", "failed", "partial", "cancelled"):
                    break
            # Verify every row used the intended rubric.
            check = qsql(
                "select count(*), count(*) filter (where "
                f"metrics->'llm_judge_rubric'->'details'->>'rubric_id' = '{rub['id']}') "
                f"from task_evaluations where evaluation_id='{eval_id}';"
            )
            n_rows, n_ok = (int(x) for x in check.split("|"))
            verified = n_rows > 0 and n_rows == n_ok
            row = {
                "task_id": task_id, "rubric_id": rub["id"],
                "generator_model_id": rub["generator_model_id"],
                "evaluation_id": eval_id, "status": status,
                "n_rows": n_rows, "verified": verified,
            }
            with log_lock:
                with LOG.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(row) + "\n")
            results.append(row)
            if not verified:
                say(f"[{prefix}] ABORT: rubric verification failed on {eval_id} "
                    f"({n_ok}/{n_rows} rows match {rub['id'][:8]})")
                break
            say(f"[{prefix}] round {i} {status}, {n_rows} rows OK")
    finally:
        if not dry:
            client.request(
                "PATCH", f"/api/projects/{CLONE}/bewertungsbogen/{active_id}",
                {"action": "activate"},
            )
            back = qsql(
                f"select id from task_rubrics where task_id='{task_id}' and status='active';"
            )
            say(f"[{prefix}] restored active {back[:8]} "
                f"({'OK' if back == active_id else 'MISMATCH!'})")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--exams", type=int, help="Limit to first N exams (smoke)")
    parser.add_argument("--rounds", type=int, help="Limit rubric rounds per exam (smoke)")
    args = parser.parse_args()

    filters = json.loads((INTERIM / "judge_run_filters_temp0.json").read_text())
    client = Client(args.base_url)
    client.login("admin@example.com", "admin")

    proj = client.request("GET", f"/api/projects/{CLONE}")
    cross_cfg = next(
        c for c in proj["evaluation_config"]["evaluation_configs"]
        if c.get("id") == CROSS_CONFIG
    )

    plans = []
    for task_id, spec in sorted(filters.items()):
        rows = qsql(
            "select id||'|'||coalesce(generator_model_id,'')||'|'||status "
            f"from task_rubrics where task_id='{task_id}' and status != 'archived' "
            "and (generation_metadata::jsonb->>'contract_version') = '3' order by id;"
        ).splitlines()
        rubs = [dict(zip(("id", "generator_model_id", "status"), r.split("|"))) for r in rows if r]
        active = [r for r in rubs if r["status"] == "active"]
        assert len(active) == 1, (task_id, len(active))
        pool = [r for r in rubs if r["status"] != "active"]
        if args.rounds:
            pool = pool[: args.rounds]
        plans.append((task_id, spec, pool, active[0]["id"]))
    if args.exams:
        plans = plans[: args.exams]

    total = sum(len(p[2]) for p in plans)
    say(f"{len(plans)} exams, {total} crossed rounds "
        f"(~{total * 3} cells, x4 judge passes)")
    if args.dry_run:
        for t, _, pool, act in plans:
            say(f"  {t[:8]}: active {act[:8]}, {len(pool)} rounds")
        return 0

    results: list = []
    threads = [
        threading.Thread(target=exam_worker,
                         args=(client, t, s, pool, act, cross_cfg, False, results))
        for t, s, pool, act in plans
    ]
    for th in threads:
        th.start()
    for th in threads:
        th.join()

    ok = sum(1 for r in results if r["verified"] and r["status"] == "completed")
    say(f"DONE: {ok}/{len(results)} rounds completed+verified")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
