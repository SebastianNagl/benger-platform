"""Import the paper-canonical Benchathon export into local dev.

Creates the project row from the export's slim project header (original id +
title + label_config preserved), then runs the platform's nested importer
(tasks + inline annotations/generations/evaluations + evaluation_runs +
human-eval blocks + korrektur comments). Idempotent guard: refuses to run if
the project id already exists.
"""

import json
import sys

from database import SessionLocal
from import_stream import run_nested_import
from models import User
from project_models import Project

PATH = "/tmp/benchathon_nested_fixed.json"


def main() -> int:
    db = SessionLocal()
    try:
        # Slim project header sits at the top of the file.
        buf = open(PATH, encoding="utf-8").read(600000)
        dec = json.JSONDecoder()
        start = buf.index("{", buf.index('"project"'))
        proj, _ = dec.raw_decode(buf[start:])
        project_id = proj["id"]

        from project_models import Task

        existing = db.query(Project).filter(Project.id == project_id).first()
        if existing is not None:
            n_tasks = db.query(Task).filter(Task.project_id == project_id).count()
            if n_tasks > 0:
                print(f"project {project_id} already has {n_tasks} tasks — aborting")
                return 1
            print(f"reusing empty project row {project_id} (prior aborted run)")

        admin = (
            db.query(User).filter(User.is_superadmin == True).first()  # noqa: E712
            or db.query(User).first()
        )
        if admin is None:
            print("no local user found to own the import")
            return 1
        print(f"importing as user {admin.email} ({admin.id})")

        if existing is None:
            project = Project(
                id=project_id,
                title=proj.get("title") or "Benchathon",
                description=proj.get("description"),
                label_config=proj.get("label_config"),
                created_by=admin.id,
            )
            db.add(project)
            db.commit()
            print(f"created project {project_id} ({project.title})")

        with open(PATH, "rb") as f:
            result = run_nested_import(db, project_id, f, str(admin.id))
        print(json.dumps(result, indent=2, default=str))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
