#!/usr/bin/env python3
"""Install the few-shot judge configs on the clone (WP A5 prep).

Two new rubric-judge configs (Luna ×3 already exists as msewfvty-24qr;
probe-luna already exists):
  - llm_judge_rubric-mini3-fewshot: Mini ×3 on the 45 picks (floor check
    under few-shot instruments). Cloned from the existing mmdi config's
    params (custom_prompt_template required) with judges = mini ×3.
  - llm_judge_rubric-probe-mini3: Mini ×3 on the probes (human:loesung only),
    cloned from probe-luna's params with judges = mini ×3.

Both T=1 (Mini provider-forced), max_tokens 12000 (matching the tailored
arm). Replace-by-id merge with backup + assertions.

Usage: uv run python scripts/ops/install_fewshot_judge_configs.py --base-url http://localhost:8001 [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
INTERIM = HERE / "data" / "interim"
CLONE_PROJECT = "81e474b8-d226-4bf8-bc2e-fb744d25cba5"

sys.path.insert(0, str(HERE / "scripts" / "ops"))
from setup_audit_project import Client  # noqa: E402

MINI3 = [{"judge_model_id": "gpt-5.4-mini", "runs": 3}]
NEW_IDS = {"llm_judge_rubric-mini3-fewshot", "llm_judge_rubric-probe-mini3"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--project", default=CLONE_PROJECT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    client = Client(args.base_url)
    client.login(os.environ.get("BENGER_ADMIN_EMAIL", "admin@example.com"),
                 os.environ.get("BENGER_ADMIN_PASSWORD", "admin"))
    project = client.request("GET", f"/api/projects/{args.project}")
    configs = (project.get("evaluation_config") or {}).get("evaluation_configs") or []
    by_id = {c["id"]: c for c in configs}

    backup = INTERIM / f"clone_eval_config_backup_{date.today().isoformat()}.json"
    backup.write_text(json.dumps(configs, ensure_ascii=False, indent=1), encoding="utf-8")

    picks_src = by_id["llm_judge_rubric-msewfvty-24qr"]   # Luna ×3 picks
    probe_src = by_id["llm_judge_rubric-probe-luna"]       # Luna ×3 probes
    p_pick = dict(picks_src["metric_parameters"]); p_pick["judges"] = MINI3
    p_probe = dict(probe_src["metric_parameters"]); p_probe["judges"] = MINI3

    new_configs = [
        {"id": "llm_judge_rubric-mini3-fewshot", "metric": "llm_judge_rubric",
         "display_name": "Few-shot picks (gpt-5.4-mini ×3)", "enabled": True,
         "prediction_fields": picks_src["prediction_fields"],
         "reference_fields": picks_src["reference_fields"], "metric_parameters": p_pick},
        {"id": "llm_judge_rubric-probe-mini3", "metric": "llm_judge_rubric",
         "display_name": "Probe (gpt-5.4-mini ×3)", "enabled": True,
         "prediction_fields": probe_src["prediction_fields"],
         "reference_fields": probe_src["reference_fields"], "metric_parameters": p_probe},
    ]

    merged = [c for c in configs if c["id"] not in NEW_IDS] + new_configs
    if args.dry_run:
        for c in new_configs:
            print(f"  {c['id']}: judges={c['metric_parameters']['judges']} "
                  f"T={c['metric_parameters'].get('temperature')} "
                  f"pred={c['prediction_fields']}")
        return 0

    client.request("PUT", f"/api/evaluations/projects/{args.project}/evaluation-config",
                   {"evaluation_configs": merged})
    check = client.request("GET", f"/api/projects/{args.project}")
    after_ids = {c["id"] for c in check["evaluation_config"]["evaluation_configs"]}
    assert NEW_IDS <= after_ids, f"missing after PUT: {NEW_IDS - after_ids}"
    assert set(by_id) <= after_ids, "pre-existing configs lost!"
    print(f"OK: {len(after_ids)} configs; installed {sorted(NEW_IDS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
