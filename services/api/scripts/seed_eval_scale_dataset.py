#!/usr/bin/env python3
"""
Seed a ZJS-scale evaluation dataset for issue #280 perf measurements.

Creates one project shaped like the prod worst case:
- --tasks tasks (default 1080) x --models models (default 6)
- 2 generations per (task, model) cell — exercises the latest-gen window
- 3 evaluation configs, one EvaluationRun each; the last run is CANCELLED
  but its rows must still feed the matrix (#278)
- per (generation, field, config): 2 TaskEvaluation rows under distinct
  judge runs with different created_at — exercises the latest-wins
  (generation_id, field_name) window and the suppressed-count math
- ~6 KB metrics blobs (padded judge justification/details) — the payload
  size is the point (#277 metrics-lite)

At --scale 1 that is tasks*models*2*3*2 rows (~78k for the defaults).
--scale N multiplies the task count.

Usage (inside the api container):
    python scripts/seed_eval_scale_dataset.py --scale 1
    python scripts/seed_eval_scale_dataset.py --cleanup

Prints the seeded project id; measure with e.g.
    curl -s -o /dev/null -w '%{time_total}\n' \
      "http://localhost:8000/api/evaluations/projects/<id>/results/by-task-model?evaluation_config_id=cfg-perfseed-1&metric=llm_judge" \
      -H "Authorization: Bearer <token>"
"""

import argparse
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

_api_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in ("/shared", os.path.join(_api_dir, "..", "shared"), _api_dir):
    if os.path.isdir(_p):
        sys.path.insert(0, os.path.abspath(_p))

from sqlalchemy import insert, text  # noqa: E402

from database import SessionLocal  # noqa: E402
from models import (  # noqa: E402
    EvaluationJudgeRun,
    EvaluationRun,
    Generation,
    ResponseGeneration,
    TaskEvaluation,
    User,
)
from project_models import Project, Task  # noqa: E402

MARKER = "perfseed-280"
PROJECT_TITLE = f"[{MARKER}] ZJS-scale eval perf dataset"
CONFIG_IDS = ["cfg-perfseed-1", "cfg-perfseed-2", "cfg-perfseed-3"]
FIELD = "answer"
METRIC_KEY = "llm_judge"


def _uid() -> str:
    return str(uuid.uuid4())


def _metrics_blob(score: float) -> dict:
    # ~6 KB, mirroring an llm_judge_falloesung row: long justification prose
    # plus a details dict — exactly what metrics-lite strips.
    return {
        METRIC_KEY: {
            "value": score,
            "method": "llm_judge",
            "justification": ("Die Falllösung behandelt die Anspruchsgrundlage "
                              "zutreffend und subsumiert sauber. ") * 60,
            "details": {
                "dimensions": [
                    {"name": f"dim_{i}", "score": (score * 10 + i) % 10,
                     "comment": "Ausführliche Begründung der Dimension. " * 8}
                    for i in range(10)
                ],
            },
            "raw": {"prompt_tokens": 4200, "completion_tokens": 900},
        }
    }


def _chunked_insert(db, table, rows, chunk=2000):
    for i in range(0, len(rows), chunk):
        db.execute(insert(table), rows[i:i + chunk])
        db.commit()


def seed(db, n_tasks: int, n_models: int) -> str:
    admin = db.query(User).filter(User.is_superadmin == True).first()  # noqa: E712
    if admin is None:
        raise SystemExit("no superadmin user in DB — seed a user first")

    now = datetime.now(timezone.utc)
    project = Project(
        id=_uid(),
        title=PROJECT_TITLE,
        description=f"marker={MARKER}",
        created_by=admin.id,
        label_config='<View><Text name="text" value="$text"/></View>',
    )
    db.add(project)
    db.commit()

    models = [f"perfseed-model-{m}" for m in range(n_models)]

    task_rows = [
        {
            "id": _uid(),
            "project_id": project.id,
            "data": {"text": f"Fall {t}: Sachverhaltstext " + "x" * 200},
            "created_by": admin.id,
            # NOT NULL with a Python-side ORM default only — core bulk
            # inserts must supply it explicitly
            "inner_id": t + 1,
        }
        for t in range(n_tasks)
    ]
    _chunked_insert(db, Task.__table__, task_rows)
    task_ids = [r["id"] for r in task_rows]

    # 2 generations per (task, model): an older and the latest.
    rg_rows, gen_rows = [], []
    gens_per_cell = []  # [(task_id, model_id, [older_gen_id, latest_gen_id])]
    for tid in task_ids:
        for mid in models:
            pair = []
            for age in (2, 0):  # hours ago; 0 = latest
                rg_id, gen_id = _uid(), _uid()
                rg_rows.append({
                    "id": rg_id, "project_id": project.id, "task_id": tid,
                    "model_id": mid, "status": "completed",
                    "created_by": admin.id,
                })
                gen_rows.append({
                    "id": gen_id, "generation_id": rg_id, "task_id": tid,
                    "model_id": mid, "run_index": 0, "case_data": "{}",
                    "response_content": "Antwort " + "y" * 500,
                    "status": "completed", "parse_status": "success",
                    "created_at": now - timedelta(hours=age),
                })
                pair.append(gen_id)
            gens_per_cell.append((tid, mid, pair))
    _chunked_insert(db, ResponseGeneration.__table__, rg_rows)
    _chunked_insert(db, Generation.__table__, gen_rows)

    # One run per config; the last one is cancelled (#278: rows still count).
    run_ids, judge_run_ids = {}, {}
    for i, cfg in enumerate(CONFIG_IDS):
        run_id = _uid()
        status = "cancelled" if i == len(CONFIG_IDS) - 1 else "completed"
        db.add(EvaluationRun(
            id=run_id, project_id=project.id, model_id=models[0],
            evaluation_type_ids=[METRIC_KEY], status=status,
            metrics={}, samples_evaluated=0,
            eval_metadata={"type": "automated", "marker": MARKER},
            created_by=admin.id,
        ))
        db.commit()
        jr_ids = []
        for run_index in (0, 1):
            jr_id = _uid()
            db.add(EvaluationJudgeRun(
                id=jr_id, evaluation_id=run_id, judge_model_id=None,
                run_index=run_index, status="completed",
            ))
            jr_ids.append(jr_id)
        db.commit()
        run_ids[cfg] = run_id
        judge_run_ids[cfg] = jr_ids

    # TaskEvaluations: per (gen, config) two rows under distinct judge runs
    # with different created_at — the older one is the rn>1 duplicate.
    te_rows = []
    for tid, mid, gen_pair in gens_per_cell:
        for gen_i, gen_id in enumerate(gen_pair):
            for cfg in CONFIG_IDS:
                base_score = round(0.3 + (hash((tid, mid, cfg)) % 60) / 100, 2)
                for dup_i, jr_id in enumerate(judge_run_ids[cfg]):
                    te_rows.append({
                        "id": _uid(),
                        "evaluation_id": run_ids[cfg],
                        "judge_run_id": jr_id,
                        "task_id": tid,
                        "generation_id": gen_id,
                        "annotation_id": None,
                        "field_name": FIELD,
                        "answer_type": "text",
                        "metrics": _metrics_blob(min(base_score + dup_i * 0.05, 1.0)),
                        "passed": True,
                        "ground_truth": {"value": "Ja"},
                        "prediction": {"value": "Ja"},
                        "evaluation_config_id": cfg,
                        "created_at": now - timedelta(minutes=30 * (1 - dup_i)),
                    })
    _chunked_insert(db, TaskEvaluation.__table__, te_rows)

    print(f"project_id={project.id}")
    print(f"tasks={len(task_ids)} models={len(models)} generations={len(gen_rows)} "
          f"task_evaluations={len(te_rows)}")
    return project.id


def cleanup(db):
    pids = [r[0] for r in db.execute(
        text("SELECT id FROM projects WHERE title LIKE :m"),
        {"m": f"[{MARKER}]%"},
    )]
    if not pids:
        print("nothing to clean up")
        return
    for pid in pids:
        for stmt in (
            "DELETE FROM task_evaluations WHERE evaluation_id IN "
            "  (SELECT id FROM evaluation_runs WHERE project_id = :pid)",
            "DELETE FROM evaluation_judge_runs WHERE evaluation_id IN "
            "  (SELECT id FROM evaluation_runs WHERE project_id = :pid)",
            "DELETE FROM evaluation_runs WHERE project_id = :pid",
            "DELETE FROM generations WHERE task_id IN "
            "  (SELECT id FROM tasks WHERE project_id = :pid)",
            "DELETE FROM response_generations WHERE project_id = :pid",
            "DELETE FROM tasks WHERE project_id = :pid",
            "DELETE FROM projects WHERE id = :pid",
        ):
            db.execute(text(stmt), {"pid": pid})
        db.commit()
        print(f"cleaned {pid}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scale", type=float, default=1.0,
                        help="task-count multiplier (1.0 ~= 78k task_evaluations)")
    parser.add_argument("--tasks", type=int, default=1080)
    parser.add_argument("--models", type=int, default=6)
    parser.add_argument("--cleanup", action="store_true")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.cleanup:
            cleanup(db)
        else:
            seed(db, int(args.tasks * args.scale), args.models)
    finally:
        db.close()


if __name__ == "__main__":
    main()
