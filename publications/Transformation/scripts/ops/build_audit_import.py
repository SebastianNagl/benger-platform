#!/usr/bin/env python3
"""Build the Bewertungsbogen-Audit nested-import file + user/assignment spec.

Consumes the BLINDED audit package's KEY.json (single source of the
per-exam blind codes — the shuffle is NOT recomputed here, so the import
can never drift from the Markdown package) plus the pulled rubric rows and
exam texts, and emits into ``data/interim/audit/``:

  - ``audit_import.json`` — nested-import payload ``{"data": [...]}``:
    one task per exam (data: name, sachverhalt, musterlösung), one
    annotation per valid rubric whose ``result`` carries the rendered
    Bewertungsbogen as a Loesung field, authored (``completed_by``) by the
    Kandidat user matching the exam's blind code.
  - ``audit_users.json`` — the Kandidat user spec (code → username/email/
    display name + a generated password) for the setup script.

The import file deliberately contains ONLY tasks + annotations (deployed
importers FK-trap on foreign evaluation/judge-run blocks).

Usage: uv run python scripts/ops/build_audit_import.py
"""

from __future__ import annotations

import json
import secrets
import string
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
AUDIT = HERE / "data" / "interim" / "audit"
KEY = AUDIT / "KEY.json"
RUBRICS = HERE / "data" / "raw" / "local" / "task_rubrics.json"
EXAMS = HERE / "data" / "interim" / "exams.json"
TASK_MAP = HERE / "data" / "interim" / "benchathon_local_task_map.json"

OUT_IMPORT = AUDIT / "audit_import.json"
OUT_USERS = AUDIT / "audit_users.json"

# One Angabe (Sachverhalt inline) + the Bogen. The Musterlösung reaches the
# grader through the modal's Referenz tab (reference_fields on the eval
# config) — a second Angabe would render as an indistinguishable "Angabe"
# collapsible (the Korrektur renderer labels extended tags by type).
LABEL_CONFIG = (
    "<View>"
    '<Angabe name="sachverhalt" value="$sachverhalt"/>'
    '<Loesung name="bogen" toName="sachverhalt"/>'
    "</View>"
)


def main() -> int:
    key = json.loads(KEY.read_text(encoding="utf-8"))
    rubrics = {
        r["id"]: r for r in json.loads(RUBRICS.read_text(encoding="utf-8"))
    }
    prod_to_local = json.loads(TASK_MAP.read_text(encoding="utf-8"))["task_id_map"]
    exams_prod = {e["task_id"]: e for e in json.loads(EXAMS.read_text(encoding="utf-8"))}
    exams = {
        local_id: exams_prod[prod_id]
        for prod_id, local_id in prod_to_local.items()
        if prod_id in exams_prod
    }

    # Kandidat users: one per blind-code LETTER, reused across exams. Codes
    # are shuffled per exam, so "Kandidat A" maps to different generators on
    # different exams — no cross-exam linkage exists to leak.
    letters = sorted({code[1] for codes in key.values() for code in codes})
    alphabet = string.ascii_letters + string.digits
    # Preserve existing credentials across rebuilds — the users may already
    # be registered on the target instance with these passwords.
    existing = {}
    if OUT_USERS.exists():
        existing = json.loads(OUT_USERS.read_text(encoding="utf-8")).get("users", {})
    users = existing or {
        f"R{letter}": {
            "username": f"audit-kandidat-{letter.lower()}",
            "email": f"audit-kandidat-{letter.lower()}@what-a-benger.net",
            "name": f"Kandidat {letter}",
            "password": "".join(secrets.choice(alphabet) for _ in range(20)),
            # placeholder — the setup script fills the real id after register
            "user_id": str(uuid.uuid4()),
        }
        for letter in letters
    } if not existing else existing

    data = []
    n_annotations = 0
    for i, (task_id, codes) in enumerate(sorted(key.items()), start=1):
        exam = exams.get(task_id) or {}
        annotations = []
        for code in sorted(codes):
            rubric_id = codes[code]["rubric_id"]
            rubric = rubrics.get(rubric_id)
            if rubric is None:
                raise SystemExit(f"rubric {rubric_id} from KEY.json not in pull")
            rendered = (rubric.get("generation_metadata") or {}).get("rendered_text")
            if not rendered:
                raise SystemExit(f"rubric {rubric_id} has no rendered_text")
            annotations.append(
                {
                    "id": f"audit-ann-{i:02d}-{code}",
                    "completed_by": users[code]["user_id"],
                    "was_cancelled": False,
                    "result": [
                        # Empty Angabe stub: the Korrektur renderer requires
                        # a result entry per field before it consults task
                        # data — without this the Sachverhalt shows as
                        # "Nicht ausgefüllt".
                        {
                            "from_name": "sachverhalt",
                            "to_name": "sachverhalt",
                            "type": "angabe",
                            "value": {"spans": [], "comments": []},
                        },
                        {
                            "from_name": "bogen",
                            "to_name": "sachverhalt",
                            "type": "loesung",
                            "value": {"markdown": rendered},
                        },
                    ],
                }
            )
            n_annotations += 1
        data.append(
            {
                "id": f"audit-task-{i:02d}",
                "data": {
                    "name": exam.get("name") or f"Exam {i:02d}",
                    "sachverhalt": exam.get("sachverhalt") or "",
                    "musterlösung": exam.get("musterloesung") or "",
                },
                "meta": {},
                "annotations": annotations,
            }
        )

    OUT_IMPORT.write_text(
        json.dumps({"data": data}, ensure_ascii=False), encoding="utf-8"
    )
    OUT_USERS.write_text(
        json.dumps(
            {"label_config": LABEL_CONFIG, "users": users},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    size_mb = OUT_IMPORT.stat().st_size / 1e6
    print(
        f"wrote audit_import.json ({len(data)} tasks, {n_annotations} "
        f"annotations, {size_mb:.1f} MB) and audit_users.json "
        f"({len(users)} Kandidat users)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
