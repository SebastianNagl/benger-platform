#!/usr/bin/env python3
"""Prepare the temperature-0 re-run on the cloned project.

1. Re-resolve the 45 picks into the clone: task ids via the importer's
   task_id_mapping; generation/annotation ids by content hash within the
   mapped task (md5(response_content) / md5(result::text) + completed_by).
2. Verify the clone's ACTIVE rubric per task equals the D6-drawn rubric
   (criteria md5 against the source rubric) — the whole experiment hangs on
   grading with the identical rubrics.
3. Write picks_temp0.json + judge_run_filters_temp0.json.
4. Write the clone's llm_judge_rubric config: copy of the source entry's
   metric_parameters with temperature FORCED to 0 (per-model clamps then
   reproduce the control arm's mixed pattern) — plus the panel judges and
   the control-mirroring prediction fields.

Usage: uv run python scripts/ops/prepare_temp0_run.py --base-url http://api.localhost
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
INTERIM = HERE / "data" / "interim"
SOURCE_PROJECT = "e529779b-300f-48c0-89cb-90f3f4b72a51"

sys.path.insert(0, str(HERE / "scripts" / "ops"))
from setup_audit_project import Client  # noqa: E402

PANEL = [
    {"judge_model_id": "gpt-5.4-mini", "runs": 3},
    {"judge_model_id": "claude-opus-4-7", "runs": 1},
    {"judge_model_id": "claude-sonnet-4-6", "runs": 1},
    {"judge_model_id": "gemini-3.1-pro-preview", "runs": 1},
    {"judge_model_id": "deepseek-ai/DeepSeek-V4-Pro", "runs": 1},
    {"judge_model_id": "Qwen/Qwen3.5-397B-A17B", "runs": 1},
]


def q(sql: str) -> str:
    return subprocess.run(
        ["docker", "exec", "benger-db-1", "psql", "-U", "postgres", "-d", "benger", "-tAc", sql],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    args = parser.parse_args()

    clone_doc = json.loads(
        subprocess.run(
            ["docker", "exec", "benger-api-1", "cat", "/tmp/temp0_clone.json"],
            capture_output=True, text=True, check=True,
        ).stdout
    )
    clone_id = clone_doc["clone_id"]
    task_map = clone_doc["mappings"]["task_id_mapping"]
    print(f"clone {clone_id}, {len(task_map)} tasks mapped")

    picks = json.loads((INTERIM / "picks.json").read_text(encoding="utf-8"))["resolved"]

    resolved, problems = [], []
    for p in picks:
        new_task = task_map[p["task_id"]]
        if p["target_type"] == "generation":
            rows = q(
                "select g2.id from generations g1 "
                "join generations g2 on md5(g2.response_content)=md5(g1.response_content) "
                f"and g2.task_id='{new_task}' and g2.model_id=g1.model_id "
                f"where g1.id='{p['target_id']}';"
            ).splitlines()
        else:
            rows = q(
                "select a2.id from annotations a1 "
                "join annotations a2 on md5(a2.result::text)=md5(a1.result::text) "
                f"and a2.task_id='{new_task}' and a2.completed_by=a1.completed_by "
                f"and a2.was_cancelled=false "
                f"where a1.id='{p['target_id']}';"
            ).splitlines()
        rows = [r for r in rows if r]
        if len(rows) != 1:
            problems.append((p["pick_id"], len(rows)))
            continue
        resolved.append({**p, "task_id": new_task, "target_id": rows[0]})
    if problems:
        print("RESOLUTION PROBLEMS:", problems)
        return 1
    (INTERIM / "picks_temp0.json").write_text(
        json.dumps({"clone_id": clone_id, "resolved": resolved, "misses": []}, indent=1),
        encoding="utf-8",
    )
    print(f"picks_temp0: {len(resolved)}/45 resolved")

    # Active-rubric identity check: clone active == source D6 draw, per task.
    sel = {
        r["task_id"]: r["rubric_id"]
        for r in json.loads((INTERIM / "active_rubric_selection.json").read_text())["selection"]
    }
    bad = 0
    for old_task, rubric_id in sel.items():
        new_task = task_map[old_task]
        row = q(
            "select (select md5(r1.criteria::text) from task_rubrics r1 "
            f"where r1.id='{rubric_id}') = md5(r2.criteria::text), count(*) over () "
            f"from task_rubrics r2 where r2.task_id='{new_task}' and r2.status='active';"
        )
        if not row.startswith("t|") or row != "t|1":
            print(f"RUBRIC MISMATCH task {old_task[:8]} -> {new_task[:8]}: {row!r}")
            bad += 1
    print("active-rubric identity:", "ALL 15 MATCH" if bad == 0 else f"{bad} BAD")
    if bad:
        return 1

    # Per-exam filters (annotator ids survive the import unchanged).
    old_filters = json.loads((INTERIM / "judge_run_filters.json").read_text(encoding="utf-8"))
    new_filters = {
        task_map[t]: {
            "model_ids": spec["model_ids"],
            "annotator_ids": spec["annotator_ids"],
            "targets": [
                r["target_id"] for r in resolved if r["task_id"] == task_map[t]
            ],
        }
        for t, spec in old_filters.items()
    }
    (INTERIM / "judge_run_filters_temp0.json").write_text(
        json.dumps(new_filters, indent=1), encoding="utf-8"
    )
    print(f"filters_temp0: {len(new_filters)} exams")

    # Fresh judge config: source metric_parameters, temperature forced to 0.
    client = Client(args.base_url)
    client.login("admin@example.com", "admin")
    source = client.request("GET", f"/api/projects/{SOURCE_PROJECT}")
    src_cfg = next(
        c for c in source["evaluation_config"]["evaluation_configs"]
        if c.get("metric") == "llm_judge_rubric"
    )
    params = dict(src_cfg["metric_parameters"])
    params["temperature"] = 0.0
    params["judges"] = PANEL
    new_cfg = {
        "id": src_cfg["id"],  # keep the id so field_name prefixes stay comparable
        "metric": "llm_judge_rubric",
        "display_name": src_cfg.get("display_name"),
        "enabled": True,
        "prediction_fields": ["__all_model__", "human:loesung"],
        "reference_fields": ["musterlösung"],
        "metric_parameters": params,
    }
    clone_proj = client.request("GET", f"/api/projects/{clone_id}")
    configs = [
        c for c in (clone_proj.get("evaluation_config") or {}).get("evaluation_configs") or []
        if c.get("metric") != "llm_judge_rubric"
    ]
    configs.append(new_cfg)
    client.request(
        "PUT",
        f"/api/evaluations/projects/{clone_id}/evaluation-config",
        {"evaluation_configs": configs},
    )
    check = client.request("GET", f"/api/projects/{clone_id}")
    cfg = next(
        c for c in check["evaluation_config"]["evaluation_configs"]
        if c.get("metric") == "llm_judge_rubric"
    )
    print("clone config: temperature =", cfg["metric_parameters"].get("temperature"),
          "| judges =", [j["judge_model_id"] for j in cfg["metric_parameters"]["judges"]],
          "| prediction_fields =", cfg["prediction_fields"])
    print("CLONE PROJECT:", clone_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
