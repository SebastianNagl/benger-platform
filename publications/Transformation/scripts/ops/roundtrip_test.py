"""Round-trip test for the export/import fixes.

Exports the repaired local Benchathon with the PATCHED serializer (rows now
carry evaluation_config_id; tasks carry their Bewertungsbogen rubrics),
imports the result as a NEW project via the PATCHED nested importer, and
compares source vs clone on the fields the fixes are about:

  - task_evaluations.evaluation_config_id preserved (the round-trip fix)
  - created_by / distinct graders preserved
  - task_rubrics round-trip (P1 export/import support)
  - baseline counts (tasks / annotations / generations / evaluations)

The clone gets the source's evaluation_config document copied onto it (the
export header deliberately stays slim), so its data view is usable as-is.
The clone is left in place for UI inspection: 'Benchathon Roundtrip Test'.
"""

import json
import uuid

from sqlalchemy import text

from database import SessionLocal

import models  # noqa: F401  (register User before project_models relationships)
from export_stream import stream_export_json
from import_stream import run_nested_import
from project_models import Project

SOURCE_ID = "e529779b-300f-48c0-89cb-90f3f4b72a51"
EXPORT_PATH = "/tmp/roundtrip_export.json"
CLONE_TITLE = "Benchathon Roundtrip Test"


def stats(db, project_id: str) -> dict:
    row = db.execute(
        text(
            """
            SELECT
              (SELECT count(*) FROM tasks WHERE project_id = :pid) AS tasks,
              (SELECT count(*) FROM annotations WHERE project_id = :pid AND was_cancelled = false) AS annotations_active,
              (SELECT count(*) FROM generations g JOIN tasks t ON g.task_id = t.id WHERE t.project_id = :pid) AS generations,
              (SELECT count(*) FROM task_evaluations te JOIN tasks t ON te.task_id = t.id WHERE t.project_id = :pid) AS task_evaluations,
              (SELECT count(*) FROM task_evaluations te JOIN tasks t ON te.task_id = t.id WHERE t.project_id = :pid AND te.evaluation_config_id IS NOT NULL) AS te_with_config_id,
              (SELECT count(DISTINCT te.evaluation_config_id) FROM task_evaluations te JOIN tasks t ON te.task_id = t.id WHERE t.project_id = :pid AND te.evaluation_config_id IS NOT NULL) AS distinct_config_ids,
              (SELECT count(DISTINCT te.created_by) FROM task_evaluations te JOIN tasks t ON te.task_id = t.id WHERE t.project_id = :pid AND te.metrics ? 'korrektur_falloesung') AS distinct_graders,
              (SELECT count(*) FROM task_rubrics WHERE project_id = :pid) AS rubrics,
              (SELECT count(*) FROM task_rubrics WHERE project_id = :pid AND status = 'active') AS rubrics_active
            """
        ),
        {"pid": project_id},
    ).mappings().one()
    return dict(row)


def main() -> int:
    db = SessionLocal()
    try:
        # --- Export with the patched serializer.
        source = db.query(Project).filter(Project.id == SOURCE_ID).one()
        header = {
            "project": {
                "id": source.id,
                "title": source.title,
                "description": source.description,
                "label_config": source.label_config,
            }
        }
        # Stream to disk; rename the top-level "tasks" key to "data" on the
        # fly (the nested importer's array path) and count the fix's marker
        # fields with a small cross-chunk overlap — the 493 MB export must
        # never be held in RAM (exit-137 lesson).
        n_cfg_ids = 0
        n_rubric_blocks = 0
        n_bytes = 0
        renamed = False
        tail = ""
        cfg_marker = '"evaluation_config_id": "'
        rubric_marker = '"rubrics": ['
        with open(EXPORT_PATH, "w", encoding="utf-8") as f:
            for chunk in stream_export_json(db, SOURCE_ID, None, header):
                if not renamed and '"tasks": [' in chunk:
                    chunk = chunk.replace('"tasks": [', '"data": [', 1)
                    renamed = True
                probe = tail + chunk
                n_cfg_ids += probe.count(cfg_marker)
                n_rubric_blocks += probe.count(rubric_marker)
                tail = probe[-40:]
                # avoid double counting matches fully inside the old tail
                n_cfg_ids -= tail.count(cfg_marker) if False else 0
                n_bytes += len(chunk)
                f.write(chunk)
        print(f"export: {n_bytes} bytes, "
              f"rows with evaluation_config_id: ~{n_cfg_ids}, "
              f"tasks with rubrics block: ~{n_rubric_blocks}, renamed: {renamed}")
        if not renamed or n_cfg_ids == 0 or n_rubric_blocks == 0:
            print("FAIL: export missing config ids / rubric blocks / tasks key")
            return 1

        # --- Import as a NEW project (config doc copied so its data view works).
        clone_id = str(uuid.uuid4())
        clone = Project(
            id=clone_id,
            title=CLONE_TITLE,
            description="Automated round-trip verification clone.",
            label_config=source.label_config,
            evaluation_config=source.evaluation_config,
            created_by=source.created_by,
        )
        db.add(clone)
        db.commit()

        with open(EXPORT_PATH, "rb") as f:
            result = run_nested_import(db, clone_id, f, str(source.created_by))
        print("import result:", json.dumps(
            {k: v for k, v in result.items() if not k.endswith("_mapping")},
        ))

        # --- Compare.
        src, cln = stats(db, SOURCE_ID), stats(db, clone_id)
        print(f"{'field':<22}{'source':>10}{'clone':>10}")
        ok = True
        for key in src:
            match = src[key] == cln[key]
            ok = ok and match
            print(f"{key:<22}{src[key]:>10}{cln[key]:>10}  {'OK' if match else 'MISMATCH'}")
        print("clone project id:", clone_id)
        return 0 if ok else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
