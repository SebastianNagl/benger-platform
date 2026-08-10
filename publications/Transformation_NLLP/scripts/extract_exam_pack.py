#!/usr/bin/env python3
"""Extract the 15 Benchathon exams (Sachverhalt + Musterlösung) from the
sibling Dataset_ARR publication's task export into data/interim/exams.json.

The export stores task content in Task.data with the umlaut key form
("musterlösung"); older/newer writers use "musterloesung". Lookups are
case-insensitive with both spellings accepted (mirrors the platform's
falloesung_tasks._get_insensitive behaviour).

Fails loudly if any exam lacks either text: the rubric-generation study
cannot tolerate silently empty inputs.
"""

from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
EXPORT = (
    HERE.parent
    / "Dataset_ARR"
    / "data"
    / "raw"
    / "benchathon"
    / "Benchathon-tasks-2026-05-31.json"
)
OUT = HERE / "data" / "interim" / "exams.json"

EXPECTED_TASKS = 15


def _norm(key: str) -> str:
    # casefold + strip diacritics so "Musterlösung" == "musterloesung" is
    # NOT assumed, but "Musterlösung" == "musterlösung" is; the oe spelling
    # is handled as an explicit alias below.
    return unicodedata.normalize("NFC", key).casefold().strip()


def get_insensitive(data: dict, *names: str) -> str | None:
    wanted = {_norm(n) for n in names}
    for key, value in data.items():
        if _norm(str(key)) in wanted and value is not None and str(value).strip():
            return str(value)
    return None


def main() -> int:
    if not EXPORT.exists():
        print(f"ERROR: export not found: {EXPORT}", file=sys.stderr)
        return 1

    with open(EXPORT, encoding="utf-8") as f:
        export = json.load(f)

    tasks = export["tasks"]
    exams = []
    problems = []
    for task in tasks:
        data = task.get("data") or {}
        sachverhalt = get_insensitive(data, "sachverhalt", "angabe")
        musterloesung = get_insensitive(data, "musterlösung", "musterloesung")
        entry = {
            "task_id": task["id"],
            "inner_id": task.get("inner_id"),
            "name": (task.get("meta") or {}).get("name") or data.get("name"),
            "bereich": get_insensitive(data, "bereich"),
            "sachverhalt": sachverhalt,
            "musterloesung": musterloesung,
        }
        if not sachverhalt:
            problems.append(f"task {task['id']} ({entry['inner_id']}): missing sachverhalt")
        if not musterloesung:
            problems.append(f"task {task['id']} ({entry['inner_id']}): missing musterlösung")
        exams.append(entry)

    if len(exams) != EXPECTED_TASKS:
        problems.append(f"expected {EXPECTED_TASKS} tasks, found {len(exams)}")

    if problems:
        for p in problems:
            print(f"ERROR: {p}", file=sys.stderr)
        return 1

    exams.sort(key=lambda e: (e["inner_id"] is None, e["inner_id"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(exams, f, ensure_ascii=False, indent=2)

    lens_sv = [len(e["sachverhalt"]) for e in exams]
    lens_ml = [len(e["musterloesung"]) for e in exams]
    print(
        f"Wrote {len(exams)} exams -> {OUT.relative_to(HERE)}\n"
        f"  sachverhalt chars: min {min(lens_sv)}, max {max(lens_sv)}\n"
        f"  musterlösung chars: min {min(lens_ml)}, max {max(lens_ml)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
