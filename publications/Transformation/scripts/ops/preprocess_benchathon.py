"""Fix uq_annotations_active_task_user violations in the Benchathon export.

The 05-31 export predates the one-active-annotation-per-(task, user)
constraint and carries duplicate empty auto-submitted timer artifacts. Per
task and completed_by, keep ONE annotation active (prefer real submissions:
not auto_submitted, then non-empty loesung content, then latest created_at)
and mark the rest was_cancelled=True. Cancelled annotations are excluded
from analyses and from the constraint's partial index, so nothing analysis-
relevant changes.

Streams data items (O(task) memory); small top-level keys are materialized.
"""

import json

import ijson

SRC = "/tmp/benchathon_nested.json"
DST = "/tmp/benchathon_nested_fixed.json"


def annotation_rank(ann):
    result = ann.get("result") or []
    has_content = any(
        (e.get("value") or {}).get("markdown") or (isinstance(e.get("value"), str) and e["value"].strip())
        for e in result
        if isinstance(e, dict)
    )
    return (
        0 if not ann.get("auto_submitted") else 1,
        0 if has_content else 1,
        # newest first among equals
        -(len(str(ann.get("created_at") or ""))),
        str(ann.get("created_at") or ""),
    )


def fix_task(task):
    anns = task.get("annotations")
    if not isinstance(anns, list):
        return 0
    groups = {}
    for ann in anns:
        if not isinstance(ann, dict) or ann.get("was_cancelled"):
            continue
        groups.setdefault(ann.get("completed_by"), []).append(ann)
    cancelled = 0
    for user, group in groups.items():
        if len(group) <= 1:
            continue
        group.sort(key=annotation_rank)
        for ann in group[1:]:
            ann["was_cancelled"] = True
            cancelled += 1
    return cancelled


def main():
    # Pass 1: all small top-level keys except the giant data array.
    small = {}
    with open(SRC, "rb") as f:
        parser = ijson.parse(f, use_float=True)
        from ijson.common import ObjectBuilder

        current, builder = None, None
        for prefix, event, value in parser:
            if prefix == "" and event == "map_key":
                if current is not None and builder is not None:
                    small[current] = builder.value
                current = value
                builder = ObjectBuilder() if value != "data" else None
                continue
            if prefix == "" and event == "end_map":
                if current is not None and builder is not None:
                    small[current] = builder.value
                continue
            if builder is not None:
                builder.event(event, value)

    print("small keys:", sorted(small.keys()))

    total_cancelled = 0
    n_tasks = 0
    with open(SRC, "rb") as f, open(DST, "w", encoding="utf-8") as out:
        out.write("{")
        first = True
        for key in ("project", "evaluation_runs"):
            if key in small:
                if not first:
                    out.write(", ")
                out.write(json.dumps(key) + ": " + json.dumps(small.pop(key)))
                first = False
        out.write(', "data": [')
        first_task = True
        for task in ijson.items(f, "data.item", use_float=True):
            n_tasks += 1
            total_cancelled += fix_task(task)
            if not first_task:
                out.write(",")
            out.write(json.dumps(task))
            first_task = False
        out.write("]")
        for key, value in small.items():
            out.write(", " + json.dumps(key) + ": " + json.dumps(value))
        out.write("}")

    print(f"tasks: {n_tasks}, duplicate active annotations cancelled: {total_cancelled}")


if __name__ == "__main__":
    main()
