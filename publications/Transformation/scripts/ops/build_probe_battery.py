#!/usr/bin/env python3
"""Build the probe battery inputs (offline; WP2.1).

Per exam, three degenerate submissions as pre-registered in DESIGN.md
(2026-08-06): verbatim Sachverhalt repetition, near-empty ("—"), and the
Musterlösung of the NEXT exam within the same bereich (cyclic by inner_id)
as the off-topic probe. Plus, pre-registered 2026-08-09: the exam's OWN
Musterlösung as the `musterloesung` positive control.

Outputs (data/interim/probes/):
- probe_texts.json: per exam the 4 probe texts + provenance
- probe_users.json: the 4 probe users (one per probe type — one user can
  hold only one active annotation per task); credentials preserved across
  reruns so setup stays idempotent (missing types are added, existing
  entries never touched)

Usage: uv run python scripts/ops/build_probe_battery.py
"""

from __future__ import annotations

import json
import secrets
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
INTERIM = HERE / "data" / "interim"
PROBES = INTERIM / "probes"

PROBE_TYPES = ("repetition", "empty", "offtopic", "musterloesung")
EMPTY_TEXT = "—"


def main() -> int:
    PROBES.mkdir(parents=True, exist_ok=True)
    exams = json.load(open(INTERIM / "exams.json"))
    by_inner = {e["inner_id"]: e for e in exams}

    # exams.json carries EXPORT task ids -> local source project ids via
    # benchathon_local_task_map.json -> clone ids via the pick files.
    export_to_local = json.load(open(INTERIM / "benchathon_local_task_map.json"))["task_id_map"]
    src = {p["pick_id"]: p["task_id"] for p in json.load(open(INTERIM / "picks.json"))["resolved"]}
    clo = {p["pick_id"]: p["task_id"] for p in json.load(open(INTERIM / "picks_temp0.json"))["resolved"]}
    local_to_clone = {}
    for pid, s_task in src.items():
        local_to_clone.setdefault(s_task, clo[pid])
        assert local_to_clone[s_task] == clo[pid], f"inconsistent clone mapping for {s_task}"
    task_map = {exp: local_to_clone[loc] for exp, loc in export_to_local.items()}
    assert len(task_map) == 15

    # Off-topic rotation: next inner_id within the same bereich, cyclic.
    by_bereich = {}
    for e in sorted(exams, key=lambda x: x["inner_id"]):
        by_bereich.setdefault(e["bereich"], []).append(e["inner_id"])
    nxt = {}
    for ids in by_bereich.values():
        assert len(ids) >= 2, "bereich with a single exam — rotation impossible"
        for i, inner in enumerate(ids):
            nxt[inner] = ids[(i + 1) % len(ids)]

    rows = []
    for e in sorted(exams, key=lambda x: x["inner_id"]):
        other = by_inner[nxt[e["inner_id"]]]
        rows.append({
            "exam_inner_id": e["inner_id"],
            "bereich": e["bereich"],
            "source_task_id": e["task_id"],
            "clone_task_id": task_map[e["task_id"]],
            "probes": {
                "repetition": e["sachverhalt"],
                "empty": EMPTY_TEXT,
                "offtopic": other["musterloesung"],
                "musterloesung": e["musterloesung"],
            },
            "offtopic_source_inner_id": other["inner_id"],
        })
    (PROBES / "probe_texts.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

    users_path = PROBES / "probe_users.json"
    users = json.load(open(users_path)) if users_path.exists() else {}
    added = [t for t in PROBE_TYPES if t not in users]
    for t in added:
        users[t] = {
            "username": f"probe-{t}",
            "email": f"probe-{t}@what-a-benger.net",
            "name": f"Probe {t.capitalize()}",
            "password": secrets.token_urlsafe(12),
            "user_id": None,
        }
    users_path.write_text(json.dumps(users, indent=1), encoding="utf-8")
    if added:
        print(f"probe_users.json: added {added}, existing credentials preserved")
    else:
        print("probe_users.json: all probe users present — credentials preserved")

    print(f"{len(rows)} exams x {len(PROBE_TYPES)} probes -> {PROBES / 'probe_texts.json'}")
    for r in rows:
        print(f"  exam {r['exam_inner_id']:2d} ({r['bereich'][:12]:12s}) "
              f"offtopic <- exam {r['offtopic_source_inner_id']:2d}, "
              f"repetition {len(r['probes']['repetition'])} chars, "
              f"offtopic {len(r['probes']['offtopic'])} chars")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
