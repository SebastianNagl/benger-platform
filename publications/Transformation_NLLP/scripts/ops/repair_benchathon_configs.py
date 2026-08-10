"""Restore per-config selectability for the imported Benchathon evaluations.

The tasks export carries neither project.evaluation_config nor the rows'
evaluation_config_id, so after import the data view can only show configs
that exist in the (fresh) project config. The original config ids survive as
the first segment of TaskEvaluation.field_name
("llm_judge_falloesung-mptmfvee-sqyx|__all_model__|musterlösung"), so:

1. backfill task_evaluations.evaluation_config_id from that prefix,
2. map the unprefixed human korrektur rows to a synthesized config id,
3. reconstruct minimal evaluation_configs entries (id, metric, display name
   incl. the judge model resolved via evaluation_judge_runs, observed
   prediction/reference fields) and merge them into
   project.evaluation_config — preserving the existing llm_judge_rubric
   entry untouched.

Idempotent: prefixes only backfill NULL rows; existing config entries with
the same id are kept as-is.
"""

import re
from collections import Counter, defaultdict

from sqlalchemy import text
from sqlalchemy.orm.attributes import flag_modified

from database import SessionLocal

# Import order matters: models registers User before project_models'
# relationships reference it (see CLAUDE.md one-shot-script rule).
import models  # noqa: F401
from project_models import Project

PROJECT_ID = "e529779b-300f-48c0-89cb-90f3f4b72a51"
KORREKTUR_CFG_ID = "korrektur_falloesung-imported-benchathon"
CONFIG_ID_RE = re.compile(r"^([a-z0-9_]+)-[a-z0-9]{6,10}-[a-z0-9]{3,6}$")

METRIC_LABELS = {
    "llm_judge_falloesung": "Falllösung Judge",
    "llm_judge_custom": "Custom Judge",
    "rouge": "ROUGE",
    "bleu": "BLEU",
    "meteor": "METEOR",
    "chrf": "chrF",
    "bertscore": "BERTScore",
    "moverscore": "MoverScore",
    "semantic_similarity": "Semantic Similarity",
}


def main() -> None:
    db = SessionLocal()
    try:
        # --- 1. Collect prefixes + field segments + judge models per config.
        rows = db.execute(
            text(
                """
                SELECT split_part(te.field_name, '|', 1) AS prefix,
                       split_part(te.field_name, '|', 2) AS pred,
                       split_part(te.field_name, '|', 3) AS ref,
                       jr.judge_model_id,
                       count(*) AS n
                FROM task_evaluations te
                JOIN tasks t ON te.task_id = t.id
                LEFT JOIN evaluation_judge_runs jr ON te.judge_run_id = jr.id
                WHERE t.project_id = :pid
                  AND te.evaluation_config_id IS NULL
                  AND te.field_name LIKE '%|%'
                GROUP BY 1, 2, 3, 4
                """
            ),
            {"pid": PROJECT_ID},
        ).fetchall()

        preds = defaultdict(Counter)
        refs = defaultdict(Counter)
        judges = defaultdict(Counter)
        totals = Counter()
        for prefix, pred, ref, judge_model, n in rows:
            m = CONFIG_ID_RE.match(prefix or "")
            if not m:
                continue
            totals[prefix] += n
            if pred:
                preds[prefix][pred] += n
            if ref:
                refs[prefix][ref] += n
            if judge_model:
                judges[prefix][judge_model] += n

        # --- 2. Backfill evaluation_config_id.
        backfilled = db.execute(
            text(
                """
                UPDATE task_evaluations te
                SET evaluation_config_id = split_part(te.field_name, '|', 1)
                FROM tasks t
                WHERE te.task_id = t.id
                  AND t.project_id = :pid
                  AND te.evaluation_config_id IS NULL
                  AND te.field_name LIKE '%|%'
                  AND split_part(te.field_name, '|', 1) ~ '^[a-z0-9_]+-[a-z0-9]{6,10}-[a-z0-9]{3,6}$'
                """
            ),
            {"pid": PROJECT_ID},
        ).rowcount

        korrektur = db.execute(
            text(
                """
                UPDATE task_evaluations te
                SET evaluation_config_id = :cfg
                FROM tasks t
                WHERE te.task_id = t.id
                  AND t.project_id = :pid
                  AND te.evaluation_config_id IS NULL
                  AND te.metrics ? 'korrektur_falloesung'
                """
            ),
            {"pid": PROJECT_ID, "cfg": KORREKTUR_CFG_ID},
        ).rowcount

        # --- 3. Rebuild the project's evaluation_configs list.
        project = db.query(Project).filter(Project.id == PROJECT_ID).one()
        cfg_doc = dict(project.evaluation_config or {})
        existing = {
            c.get("id"): c
            for c in cfg_doc.get("evaluation_configs") or []
            if isinstance(c, dict)
        }

        new_entries = []
        for prefix, n in sorted(totals.items(), key=lambda kv: -kv[1]):
            if prefix in existing:
                continue
            metric = CONFIG_ID_RE.match(prefix).group(1)
            label = METRIC_LABELS.get(metric, metric)
            judge = judges[prefix].most_common(1)
            display = (
                f"{label} ({judge[0][0]})" if judge and judge[0][0] else label
            )
            suffix = prefix.rsplit("-", 2)[-2:]
            display = f"{display} [{'-'.join(suffix)}]"
            new_entries.append(
                {
                    "id": prefix,
                    "metric": metric,
                    "display_name": display,
                    "enabled": True,
                    "prediction_fields": [p for p, _ in preds[prefix].most_common(3)],
                    "reference_fields": [r for r, _ in refs[prefix].most_common(2)],
                    "metric_parameters": {},
                    "imported_from_field_name": True,
                }
            )

        if korrektur and KORREKTUR_CFG_ID not in existing:
            new_entries.append(
                {
                    "id": KORREKTUR_CFG_ID,
                    "metric": "korrektur_falloesung",
                    "display_name": "Korrektur (Standard Falllösung, importiert)",
                    "enabled": True,
                    "prediction_fields": ["human:loesung"],
                    "reference_fields": ["task.musterlösung"],
                    "metric_parameters": {},
                    "imported_from_field_name": True,
                }
            )

        cfg_doc["evaluation_configs"] = list(existing.values()) + new_entries
        project.evaluation_config = cfg_doc
        flag_modified(project, "evaluation_config")
        db.commit()

        print(f"backfilled prefixed rows: {backfilled}")
        print(f"backfilled korrektur rows: {korrektur}")
        print(f"config entries now: {len(cfg_doc['evaluation_configs'])} "
              f"({len(new_entries)} reconstructed)")
        for e in cfg_doc["evaluation_configs"]:
            print(f"  - {e['metric']:<24} {e['display_name']}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
