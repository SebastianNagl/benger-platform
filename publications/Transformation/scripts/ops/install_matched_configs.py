#!/usr/bin/env python3
"""Install the matched holistic-arm judge configs on the Temp0 clone (WP1.2).

Adds two ``llm_judge_falloesung`` entries — Luna ×3 and GPT-5.4-Mini ×3 — for
the reviewer-required matched baseline: the same judge grading the identical
45 cells under BOTH instruments. Parameters mirror the recovered control-arm
spec (GPT-5 line provider-forced T=1; control primary ran max_tokens 16000).

SAFETY: replace-by-id merge ONLY. The clone carries 7 imported falloesung
configs with empty metric_parameters whose ids key 5,278 control rows via
field_name prefixes — filtering the list by metric would orphan them all.
The full pre-PUT config list is backed up to data/interim/.

Usage:
  uv run python scripts/ops/install_matched_configs.py --base-url http://api.localhost [--dry-run]
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

NEW_CONFIGS = [
    {
        "id": "llm_judge_falloesung-luna3-matched",
        "metric": "llm_judge_falloesung",
        "display_name": "Falllösung Judge MATCHED (gpt-5.6-luna ×3)",
        "enabled": True,
        "prediction_fields": ["__all_model__", "human:loesung"],
        "reference_fields": ["musterlösung"],
        "metric_parameters": {
            "temperature": 1,
            "max_tokens": 16000,
            "judges": [{"judge_model_id": "gpt-5.6-luna", "runs": 3}],
        },
    },
    {
        "id": "llm_judge_falloesung-mini3-matched",
        "metric": "llm_judge_falloesung",
        "display_name": "Falllösung Judge MATCHED (gpt-5.4-mini ×3)",
        "enabled": True,
        "prediction_fields": ["__all_model__", "human:loesung"],
        "reference_fields": ["musterlösung"],
        "metric_parameters": {
            "temperature": 1,
            "max_tokens": 16000,
            "judges": [{"judge_model_id": "gpt-5.4-mini", "runs": 3}],
        },
    },
]
NEW_IDS = {c["id"] for c in NEW_CONFIGS}


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

    backup = INTERIM / f"clone_eval_config_backup_{date.today().isoformat()}.json"
    backup.write_text(json.dumps(configs, ensure_ascii=False, indent=1), encoding="utf-8")

    old_fall_ids = sorted(
        c["id"] for c in configs
        if c.get("metric") == "llm_judge_falloesung" and c["id"] not in NEW_IDS
    )
    print(f"project {args.project}: {len(configs)} configs "
          f"({len(old_fall_ids)} imported falloesung); backup -> {backup.name}")

    merged = [c for c in configs if c.get("id") not in NEW_IDS] + NEW_CONFIGS
    if args.dry_run:
        print(f"DRY RUN: would PUT {len(merged)} configs "
              f"(+{len(merged) - len(configs) if len(merged) > len(configs) else 0} new)")
        for c in NEW_CONFIGS:
            print(f"  {c['id']}: {c['metric_parameters']}")
        return 0

    client.request(
        "PUT",
        f"/api/evaluations/projects/{args.project}/evaluation-config",
        {"evaluation_configs": merged},
    )

    check = client.request("GET", f"/api/projects/{args.project}")
    after = (check.get("evaluation_config") or {}).get("evaluation_configs") or []
    after_ids = {c["id"] for c in after}

    missing_old = [i for i in old_fall_ids if i not in after_ids]
    assert not missing_old, f"IMPORTED FALLOESUNG CONFIGS LOST: {missing_old}"
    assert NEW_IDS <= after_ids, f"new configs missing after PUT: {NEW_IDS - after_ids}"
    for want in NEW_CONFIGS:
        got = next(c for c in after if c["id"] == want["id"])
        assert got["metric_parameters"] == want["metric_parameters"], (
            f"{want['id']}: params not echoed: {got['metric_parameters']}")
        assert got["prediction_fields"] == want["prediction_fields"]
    print(f"OK: {len(after)} configs after PUT "
          f"(was {len(configs)}); all {len(old_fall_ids)} imported falloesung ids intact; "
          f"new params echoed for {sorted(NEW_IDS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
