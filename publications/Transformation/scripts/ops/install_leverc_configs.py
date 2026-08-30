#!/usr/bin/env python3
"""Install lever-C configs on the Temp0 clone (multi-judge matched, WP C0+C1).

Three configs, same replace-by-id safety as install_matched_configs.py
(backup + assertions + never filter by metric):

- llm_judge_rubric-msc0vokl-mmdi-rep3-sonnetfix: sonnet ×3 tailored-arm
  repair (T=0, max_tokens 12000) for the 12 credit-exhausted targets — a
  sonnet-ONLY copy so re-dispatch doesn't resample the intact DS/Qwen cells.
- llm_judge_falloesung-rep3-matched: holistic sonnet/DS-Pro/Qwen ×3 (T=0).
- llm_judge_falloesung-gem3-matched: holistic gemini ×3 (T=1).

Holistic arms use max_tokens 16000 to match the already-run Luna/Mini
matched arms and the control repeat config. NOTE (UI gap, worth an issue):
the Falllösung judge wizard caps Max Tokens at 8192 via HTML validation, so
a 16000 control-matched arm cannot be authored through the UI — hence this
script. Everything else in the wizard (primary judge, runs-per-judge,
ensemble, temperature) works and was verified.

Usage:
  uv run python scripts/ops/install_leverc_configs.py --base-url http://api.localhost [--dry-run]
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

# The sonnet-repair config must be a byte-identical clone of the existing
# -rep3 rubric config (incl. custom_prompt_template — required by the
# validator) with judges narrowed to sonnet only. Loaded at runtime from the
# clone's live config so it can never drift from the arm it repairs.
BACKUP_REP3_SOURCE = "llm_judge_rubric-msc0vokl-mmdi-rep3"

NEW_CONFIGS = [
    {
        "id": "llm_judge_falloesung-rep3-matched",
        "metric": "llm_judge_falloesung",
        "display_name": "Falllösung MATCHED (sonnet/DS-Pro/Qwen ×3)",
        "enabled": True,
        "prediction_fields": ["__all_model__", "human:loesung"],
        "reference_fields": ["musterlösung"],
        "metric_parameters": {
            "temperature": 0.0,
            "max_tokens": 16000,
            "judges": [
                {"judge_model_id": "claude-sonnet-4-6", "runs": 3},
                {"judge_model_id": "deepseek-ai/DeepSeek-V4-Pro", "runs": 3},
                {"judge_model_id": "Qwen/Qwen3.5-397B-A17B", "runs": 3},
            ],
        },
    },
    {
        "id": "llm_judge_falloesung-gem3-matched",
        "metric": "llm_judge_falloesung",
        "display_name": "Falllösung MATCHED (gemini ×3)",
        "enabled": True,
        "prediction_fields": ["__all_model__", "human:loesung"],
        "reference_fields": ["musterlösung"],
        "metric_parameters": {
            "temperature": 1,
            "max_tokens": 16000,
            "judges": [{"judge_model_id": "gemini-3.1-pro-preview", "runs": 3}],
        },
    },
]
SONNETFIX_ID = "llm_judge_rubric-msc0vokl-mmdi-rep3-sonnetfix"
NEW_IDS = {c["id"] for c in NEW_CONFIGS} | {SONNETFIX_ID}


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

    # Build the sonnet-repair config from the live -rep3 config (clone its
    # params incl. custom_prompt_template; narrow judges to sonnet ×3).
    src = next((c for c in configs if c["id"] == BACKUP_REP3_SOURCE), None)
    assert src is not None, f"source config {BACKUP_REP3_SOURCE} not found on project"
    sonnetfix_params = dict(src["metric_parameters"])
    sonnetfix_params["judges"] = [{"judge_model_id": "claude-sonnet-4-6", "runs": 3}]
    NEW_CONFIGS.insert(0, {
        "id": SONNETFIX_ID,
        "metric": "llm_judge_rubric",
        "display_name": "Repeats T0 x3 — sonnet fix",
        "enabled": True,
        "prediction_fields": src.get("prediction_fields") or ["__all_model__", "human:loesung"],
        "reference_fields": src.get("reference_fields") or ["musterlösung"],
        "metric_parameters": sonnetfix_params,
    })

    preexisting = {c["id"] for c in configs}
    print(f"project {args.project}: {len(configs)} configs; backup -> {backup.name}")

    merged = [c for c in configs if c.get("id") not in NEW_IDS] + NEW_CONFIGS
    if args.dry_run:
        print(f"DRY RUN: would PUT {len(merged)} configs")
        for c in NEW_CONFIGS:
            tag = "REPLACE" if c["id"] in preexisting else "NEW"
            print(f"  [{tag}] {c['id']}: {c['metric_parameters']}")
        return 0

    client.request("PUT", f"/api/evaluations/projects/{args.project}/evaluation-config",
                   {"evaluation_configs": merged})

    check = client.request("GET", f"/api/projects/{args.project}")
    after = (check.get("evaluation_config") or {}).get("evaluation_configs") or []
    after_ids = {c["id"] for c in after}

    lost = [i for i in preexisting if i not in after_ids and i not in NEW_IDS]
    assert not lost, f"PRE-EXISTING CONFIGS LOST: {lost}"
    assert NEW_IDS <= after_ids, f"new configs missing after PUT: {NEW_IDS - after_ids}"
    for want in NEW_CONFIGS:
        got = next(c for c in after if c["id"] == want["id"])
        assert got["metric_parameters"] == want["metric_parameters"], (
            f"{want['id']}: params not echoed: {got['metric_parameters']}")
    print(f"OK: {len(after)} configs after PUT (was {len(configs)}); "
          f"all {len(preexisting)} pre-existing ids intact; new params echoed for {sorted(NEW_IDS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
