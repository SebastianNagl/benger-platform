#!/usr/bin/env python3
"""Dispatch pick-scoped tailored-arm judge runs (RQ2/RQ3 main arm).

One evaluation run per exam, scoped with ``task_ids=[task]`` +
``model_ids``/``annotator_user_ids`` from ``judge_run_filters.json`` (derived
from picks.json). Three exams over-select one sibling generation from the
same model (filters can't address individual generations); analysis filters
to the exact 45 target ids, so the extras are judged-and-ignored.

The single ``llm_judge_rubric`` config (6-judge Config-B panel, primary
gpt-5.4-mini runs=3) is read live from the project so the run always uses
the currently stored panel. force_rerun=True: cells must be judged under the
NEWLY activated D6 rubrics, not skipped because pilot rows exist.

Usage:
  uv run python scripts/ops/run_judge_evals.py --base-url http://api.localhost \
      [--task <task_id>] [--dry-run]

Logs one JSONL row per dispatched run to data/interim/judge_run_log.jsonl.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
DEFAULT_FILTERS = HERE / "data" / "interim" / "judge_run_filters.json"
DEFAULT_LOG = HERE / "data" / "interim" / "judge_run_log.jsonl"
DEFAULT_PROJECT = "e529779b-300f-48c0-89cb-90f3f4b72a51"

sys.path.insert(0, str(HERE / "scripts" / "ops"))
from setup_audit_project import Client  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--task", help="Dispatch only this task (smoke mode)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--poll", action="store_true", help="Wait for each run to finish")
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--filters", default=str(DEFAULT_FILTERS))
    parser.add_argument("--log", default=str(DEFAULT_LOG))
    parser.add_argument("--config-id", help="Dispatch only these config entries (comma-separated ids)")
    parser.add_argument(
        "--metric", default="llm_judge_rubric",
        help="Metric family of the configs to dispatch "
             "(llm_judge_falloesung for the matched holistic arms)",
    )
    args = parser.parse_args()
    project_id = args.project
    log_path = Path(args.log)

    filters = json.loads(Path(args.filters).read_text(encoding="utf-8"))
    if args.task:
        filters = {args.task: filters[args.task]}

    client = Client(args.base_url)
    client.login(os.environ.get("BENGER_ADMIN_EMAIL", "admin@example.com"),
                 os.environ.get("BENGER_ADMIN_PASSWORD", "admin"))
    project = client.request("GET", f"/api/projects/{project_id}")
    # ALL llm_judge_rubric entries are dispatched together — the temp-0
    # re-run splits gemini into its own T=1 entry to replicate the control
    # arm's per-judge temperature pattern exactly.
    wanted = set(args.config_id.split(",")) if args.config_id else None
    rubric_cfgs = [
        c
        for c in project["evaluation_config"]["evaluation_configs"]
        if c.get("metric") == args.metric
        and (wanted is None or c.get("id") in wanted)
    ]
    # Without an explicit judges list, _resolve_judges falls back to the
    # platform's legacy default judge — refuse rather than judge with it.
    missing = [
        c["id"] for c in rubric_cfgs
        if not (c.get("metric_parameters") or {}).get("judges")
    ]
    if missing:
        print(f"REFUSING dispatch — configs without explicit judges list: {missing}")
        return 1
    for c in rubric_cfgs:
        params = c.get("metric_parameters") or {}
        print(
            f"config {c['id']} (T={params.get('temperature')}): "
            f"{[(j['judge_model_id'], j.get('runs', 1)) for j in params['judges']]}"
        )

    for task_id in sorted(filters):
        spec = filters[task_id]
        body = {
            "project_id": project_id,
            "evaluation_configs": rubric_cfgs,
            "force_rerun": True,
            "task_ids": [task_id],
            "model_ids": spec["model_ids"] or None,
            "annotator_user_ids": spec["annotator_ids"] or None,
        }
        print(
            f"{task_id[:8]}: models={spec['model_ids']} "
            f"annotators={[a[:8] for a in spec['annotator_ids']]} "
            f"targets={len(spec['targets'])}"
        )
        if args.dry_run:
            continue
        resp = client.request("POST", "/api/evaluations/run", body)
        row = {
            "task_id": task_id,
            "evaluation_id": resp.get("evaluation_id"),
            "status": resp.get("status"),
            "filters": spec,
        }
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
        print(f"  -> evaluation_id={resp.get('evaluation_id')} status={resp.get('status')}")
        if args.poll:
            _poll(client, resp["evaluation_id"])
    return 0


def _poll(client: Client, evaluation_id: str) -> None:
    while True:
        time.sleep(15)
        res = client.request("GET", f"/api/evaluations/run/results/{evaluation_id}")
        status = res.get("status")
        print(f"  poll {evaluation_id[:8]}: {status}")
        if status in ("completed", "failed", "partial"):
            return


if __name__ == "__main__":
    raise SystemExit(main())
