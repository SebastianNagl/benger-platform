#!/usr/bin/env python3
"""D10(b): automated audit — LLM judge over the 170 blinded audit items.

Adds an ``llm_judge_custom`` config (multidim single-call, the 7 human audit
dimensions verbatim from ``setup_audit_project.AUDIT_CRITERIA``) to the audit
project and dispatches pick-free runs over ALL audit annotations (the 12
Kandidat blind-code users). The auditor is a roster model (gpt-5.4-mini), so
results are reported with a self-vs-other split via KEY.json; per D10 the
audit is labeled screening and NEVER feeds rubric selection.

The judge sees exactly what a human auditor sees: Sachverhalt, Musterlösung,
and the blinded Bogen markdown — generator identity appears nowhere.

Usage:
  uv run python scripts/ops/run_automated_audit.py --base-url http://api.localhost \
      [--task <local_audit_task_id>] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
AUDIT_DIR = HERE / "data" / "interim" / "audit"
LOG = HERE / "data" / "interim" / "automated_audit_runs.jsonl"

sys.path.insert(0, str(HERE / "scripts" / "ops"))
from setup_audit_project import AUDIT_CRITERIA, Client  # noqa: E402

PROJECT_ID = "687cc09b-7589-44cd-8450-62b85eefd1da"
ORG_ID = "ee3064db-276e-404c-9cfb-4fe594506196"
AUDITOR_MODEL = "gpt-5.4-mini"
CONFIG_ID = "llm_judge_custom-auto-audit"


def _dimensions_block() -> str:
    lines = []
    for key, d in AUDIT_CRITERIA.items():
        lines.append(f"- **{key}** ({d['name']}, 1-{d['max_score']}): {d['description']} {d['rubric']}")
    return "\n".join(lines)


PROMPT_TEMPLATE = f"""Du bist ein erfahrener juristischer Prüfer und begutachtest einen \
maschinell erstellten Bewertungsbogen (Rohpunkteschema, 100 Punkte) für eine \
juristische Klausuraufgabe. Beurteile ausschließlich den Bogen — nicht die \
Musterlösung und nicht den Sachverhalt.

# Sachverhalt
{{sachverhalt}}

# Musterlösung
{{musterlösung}}

# Zu begutachtender Bewertungsbogen
{{bogen}}

# Bewertungsdimensionen
Bewerte den Bogen auf jeder der folgenden Dimensionen (Skala 1-5, halbe \
Punkte sind nicht zulässig):

{_dimensions_block()}

Begründe jede Dimensionsbewertung kurz und konkret mit Bezug auf einzelne \
Prüfungsschritte des Bogens. Schließe mit einer knappen Gesamtwürdigung. \
Antworte ausschließlich im geforderten JSON-Format."""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--task", help="Restrict to one audit task (smoke mode)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    client = Client(args.base_url)
    client.login("admin@example.com", "admin")
    org_headers = {"X-Organization-Context": ORG_ID}

    project = client.request("GET", f"/api/projects/{PROJECT_ID}", headers=org_headers)
    configs = [
        c
        for c in project["evaluation_config"]["evaluation_configs"]
        if c.get("id") != CONFIG_ID
    ]
    audit_cfg = {
        "id": CONFIG_ID,
        "metric": "llm_judge_custom",
        "display_name": "Automatisierter Bewertungsbogen-Audit",
        "enabled": True,
        # "human:" prefix is load-bearing: unprefixed fields classify as
        # LLM-side and the run would fan out ZERO annotation cells
        # (eval_field_classification.classify_pred_fields).
        "prediction_fields": ["human:bogen"],
        "reference_fields": ["musterlösung"],
        "metric_parameters": {
            "judges": [{"judge_model_id": AUDITOR_MODEL, "runs": 1}],
            "custom_criteria": AUDIT_CRITERIA,
            "custom_prompt_template": PROMPT_TEMPLATE,
            "temperature": 0.0,
            "max_tokens": 8000,
        },
    }
    configs.append(audit_cfg)
    if args.dry_run:
        print("DRY RUN — config that would be written:")
        print(json.dumps(audit_cfg, indent=1, ensure_ascii=False)[:2000])
        return 0

    client.request(
        "PUT",
        f"/api/evaluations/projects/{PROJECT_ID}/evaluation-config",
        {"evaluation_configs": configs},
        headers=org_headers,
    )
    print(f"config {CONFIG_ID} written ({len(configs)} entries)")

    # No annotator filter: every non-cancelled annotation on this project IS
    # an audit item (the 170 blinded Bögen by the 12 Kandidat stub users) —
    # and audit_users.json holds pre-rebuild user ids that would 400 anyway.
    body = {
        "project_id": PROJECT_ID,
        "evaluation_configs": [audit_cfg],
        "force_rerun": True,
        "task_ids": [args.task] if args.task else None,
    }
    resp = client.request("POST", "/api/evaluations/run", body, headers=org_headers)
    row = {
        "evaluation_id": resp.get("evaluation_id"),
        "status": resp.get("status"),
        "task_scope": args.task or "ALL",
        "auditor": AUDITOR_MODEL,
    }
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
    print(f"dispatched: {row}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
