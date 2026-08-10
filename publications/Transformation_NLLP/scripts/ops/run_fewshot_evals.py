#!/usr/bin/env python3
"""Judge the drawn few-shot rubrics (WP A5).

Per exam (parallel across exams, serial within): activate the drawn few-shot
rubric, dispatch in that window
  - PICKS run: [Luna ×3, Mini ×3] with the pick filters (judge_run_filters_temp0)
  - PROBE run: [probe-luna, probe-mini3] with the probe filters (probe_run_filters)
wait both terminal, verify every row's details.rubric_id == the drawn few-shot
rubric, then restore the D6 active rubric. Each /run call gets a fresh
evaluation_id, so these rows never overwrite the existing D6 arm data;
extraction keys on this run's log.

CRITICAL: must not run concurrently with any other rubric-activation work.

Output: data/interim/fewshot_run_log.jsonl (one line per exam per run kind).

Usage: uv run python scripts/ops/run_fewshot_evals.py --base-url http://localhost:8001 [--dry-run] [--exams N]
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
LOG = INTERIM / "fewshot_run_log.jsonl"
CLONE = "81e474b8-d226-4bf8-bc2e-fb744d25cba5"
PICK_CONFIGS = ["llm_judge_rubric-msewfvty-24qr", "llm_judge_rubric-mini3-fewshot"]
PROBE_CONFIGS = ["llm_judge_rubric-probe-luna", "llm_judge_rubric-probe-mini3"]

sys.path.insert(0, str(HERE / "scripts" / "ops"))
from setup_audit_project import Client  # noqa: E402

log_lock = threading.Lock()
print_lock = threading.Lock()


def say(m):
    with print_lock:
        print(m, flush=True)


def qsql(sql):
    return subprocess.run(
        ["docker", "exec", "benger-db-1", "psql", "-U", "postgres", "-d", "benger", "-tAc", sql],
        capture_output=True, text=True, check=True).stdout.strip()


def dispatch_wait_verify(client, task_id, rubric_id, cfgs, spec, kind, results):
    body = {"project_id": CLONE, "evaluation_configs": cfgs, "force_rerun": True,
            "task_ids": [task_id],
            "model_ids": spec.get("model_ids") or None,
            "annotator_user_ids": spec.get("annotator_ids") or None}
    resp = client.request("POST", "/api/evaluations/run", body)
    eval_id = resp["evaluation_id"]
    status = "running"
    for _ in range(360):  # 90 min cap
        time.sleep(15)
        status = qsql(f"select status from evaluation_runs where id='{eval_id}';") or "missing"
        if status in ("completed", "failed", "partial", "cancelled"):
            break
    check = qsql(
        "select count(*), count(*) filter (where "
        f"metrics->'llm_judge_rubric'->'details'->>'rubric_id' = '{rubric_id}') "
        f"from task_evaluations where evaluation_id='{eval_id}';")
    n_rows, n_ok = (int(x) for x in check.split("|"))
    verified = n_rows > 0 and n_rows == n_ok
    row = {"task_id": task_id, "rubric_id": rubric_id, "kind": kind,
           "evaluation_id": eval_id, "status": status, "n_rows": n_rows, "verified": verified}
    with log_lock:
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
    results.append(row)
    return row


def exam_worker(client, task_id, pick_spec, probe_spec, drawn_id, active_id,
                pick_cfgs, probe_cfgs, dry, results):
    prefix = task_id[:8]
    try:
        say(f"[{prefix}] activate few-shot {drawn_id[:8]}")
        if dry:
            return
        client.request("PATCH", f"/api/projects/{CLONE}/bewertungsbogen/{drawn_id}",
                       {"action": "activate"})
        for kind, cfgs, spec in (("picks", pick_cfgs, pick_spec),
                                 ("probes", probe_cfgs, probe_spec)):
            if spec is None:
                continue
            r = dispatch_wait_verify(client, task_id, drawn_id, cfgs, spec, kind, results)
            flag = "OK" if r["verified"] else "VERIFY-FAIL"
            say(f"[{prefix}] {kind} {r['status']} {r['n_rows']} rows {flag}")
            if not r["verified"]:
                say(f"[{prefix}] ABORT ({kind})")
                break
    finally:
        if not dry:
            client.request("PATCH", f"/api/projects/{CLONE}/bewertungsbogen/{active_id}",
                           {"action": "activate"})
            back = qsql(f"select id from task_rubrics where task_id='{task_id}' and status='active';")
            say(f"[{prefix}] restored active {back[:8]} ({'OK' if back == active_id else 'MISMATCH!'})")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--exams", type=int)
    parser.add_argument("--no-probes", action="store_true", help="Judge picks only")
    args = parser.parse_args()

    selection = json.loads((INTERIM / "fewshot" / "selection.json").read_text())["selection"]
    pick_filters = json.loads((INTERIM / "judge_run_filters_temp0.json").read_text())
    probe_filters = json.loads((INTERIM / "probe_run_filters.json").read_text())
    d6 = json.loads((INTERIM / "clone_d6_actives.json").read_text())  # clone task -> D6 rubric id

    client = Client(args.base_url)
    import os
    client.login(os.environ.get("BENGER_ADMIN_EMAIL", "admin@example.com"),
                 os.environ.get("BENGER_ADMIN_PASSWORD", "admin"))

    # /api/evaluations/run wants full config OBJECTS, not id strings.
    proj = client.request("GET", f"/api/projects/{CLONE}")
    by_id = {c["id"]: c for c in proj["evaluation_config"]["evaluation_configs"]}
    pick_cfgs = [by_id[i] for i in PICK_CONFIGS]
    probe_cfgs = [by_id[i] for i in PROBE_CONFIGS]

    plans = []
    for s in selection:
        t = s["task_id"]
        plans.append((t, pick_filters.get(t),
                      None if args.no_probes else probe_filters.get(t),
                      s["rubric_id"], d6[t]))
    if args.exams:
        plans = plans[:args.exams]

    say(f"{len(plans)} exams; pick configs {PICK_CONFIGS}; "
        f"probe configs {'(skipped)' if args.no_probes else PROBE_CONFIGS}")
    if args.dry_run:
        for t, ps, pr, drawn, act in plans:
            say(f"  {t[:8]}: draw {drawn[:8]} active {act[:8]} "
                f"picks={'y' if ps else 'n'} probes={'y' if pr else 'n'}")
        return 0

    results = []
    threads = [threading.Thread(target=exam_worker,
               args=(client, t, ps, pr, drawn, act, pick_cfgs, probe_cfgs, False, results))
               for t, ps, pr, drawn, act in plans]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    ok = sum(1 for r in results if r["verified"] and r["status"] == "completed")
    say(f"DONE: {ok}/{len(results)} runs completed+verified")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
