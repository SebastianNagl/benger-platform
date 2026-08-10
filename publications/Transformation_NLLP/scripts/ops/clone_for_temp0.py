#!/usr/bin/env python3
"""Clone the Benchathon project for the temperature-0 judge re-run.

Runs INSIDE the api container (docker cp + docker exec python). Streams the
export to disk (never in RAM — exit-137 lesson), imports it as the new
project "Benchathon Temp0 Rerun", and writes the old->new id mappings that
the pick re-resolution needs to /tmp/temp0_clone.json.

The clone starts with the SOURCE evaluation_config so its data view works;
the judge entry is overwritten host-side afterwards with an explicit
temperature-0 config (the whole point of the re-run).
"""

import json
import sys
import uuid

# python /tmp/script.py puts /tmp (not cwd) on sys.path — add the app layout.
sys.path.insert(0, "/app")
sys.path.insert(0, "/shared")

from sqlalchemy import text

from database import SessionLocal

import models  # noqa: F401  (register User before project_models relationships)
from export_stream import stream_export_json
from import_stream import run_nested_import
from project_models import Project

SOURCE_ID = "e529779b-300f-48c0-89cb-90f3f4b72a51"
EXPORT_PATH = "/tmp/temp0_export.json"
OUT = "/tmp/temp0_clone.json"
CLONE_TITLE = "Benchathon Temp0 Rerun"


def stats(db, project_id: str) -> dict:
    row = db.execute(
        text(
            """
            SELECT
              (SELECT count(*) FROM tasks WHERE project_id = :pid) AS tasks,
              (SELECT count(*) FROM annotations WHERE project_id = :pid AND was_cancelled = false) AS annotations_active,
              (SELECT count(*) FROM generations g JOIN tasks t ON g.task_id = t.id WHERE t.project_id = :pid) AS generations,
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
        source = db.query(Project).filter(Project.id == SOURCE_ID).one()
        header = {
            "project": {
                "id": source.id,
                "title": source.title,
                "description": source.description,
                "label_config": source.label_config,
            }
        }
        n_bytes, renamed = 0, False
        with open(EXPORT_PATH, "w", encoding="utf-8") as f:
            for chunk in stream_export_json(db, SOURCE_ID, None, header):
                if not renamed and '"tasks": [' in chunk:
                    chunk = chunk.replace('"tasks": [', '"data": [', 1)
                    renamed = True
                n_bytes += len(chunk)
                f.write(chunk)
        print(f"export: {n_bytes} bytes, renamed: {renamed}")
        if not renamed:
            print("FAIL: export missing tasks key")
            return 1

        clone_id = str(uuid.uuid4())
        clone = Project(
            id=clone_id,
            title=CLONE_TITLE,
            description="Isolated clone for the temperature-0 judge re-run (2026-08-04).",
            label_config=source.label_config,
            evaluation_config=source.evaluation_config,
            created_by=source.created_by,
        )
        db.add(clone)
        db.commit()

        with open(EXPORT_PATH, "rb") as f:
            result = run_nested_import(db, clone_id, f, str(source.created_by))
        summary = {k: v for k, v in result.items() if not k.endswith("_mapping")}
        print("import result:", json.dumps(summary))

        mappings = {
            k: v for k, v in result.items()
            if k.endswith("_mapping") and isinstance(v, dict)
        }
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump(
                {"clone_id": clone_id, "mappings": mappings, "summary": summary},
                f,
            )
        print("mapping keys:", {k: len(v) for k, v in mappings.items()})

        src, cln = stats(db, SOURCE_ID), stats(db, clone_id)
        ok = True
        for key in src:
            match = src[key] == cln[key]
            ok = ok and match
            print(f"{key:<20}{src[key]:>8}{cln[key]:>8}  {'OK' if match else 'MISMATCH'}")
        print("clone project id:", clone_id)
        return 0 if ok else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
