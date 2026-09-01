#!/usr/bin/env python3
"""Build few-shot exemplars and write them onto the clone tasks (WP A1).

Pre-registered rule (DESIGN.md 2026-08-06): for each target exam, ONE
exemplar drawn from the NEXT same-bereich exam (cyclic by inner_id, the
probe battery's rotation family). The exemplar rubric is that exam's
outcome winner: minimum Luna 3-pass repeat SD among its v3 rubrics SUBJECT
TO MAE <= that exam's cross-source median MAE (blocks reliability winners
with catastrophic harshness). Length guard: if the winner's full_document
JSON > 30k chars, step to the next same-bereich exam and repeat.

Exemplar payload = the winner's generation_metadata.full_document (the
model's own pre-derivation JSON — never rendered/derived, which would teach
code-computed fields the contract forbids the model to emit), wrapped in a
labeled German BEISPIEL block with framing that the exemplar is from a
DIFFERENT exam and only its structure/operationalization should be imitated.

Writes each target CLONE task's data.exemplar_rubrics via
PUT /api/projects/{clone}/tasks/{task} (merge semantics). Snapshots the
assignment to data/interim/fewshot/exemplars.json.

Usage: uv run python scripts/ops/build_fewshot_exemplars.py --base-url http://localhost:8001 [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
INTERIM = HERE / "data" / "interim"
FEWSHOT = INTERIM / "fewshot"
CLONE_PROJECT = "81e474b8-d226-4bf8-bc2e-fb744d25cba5"
MAX_EXEMPLAR_CHARS = 30_000

sys.path.insert(0, str(HERE / "scripts" / "ops"))
from setup_audit_project import Client  # noqa: E402

FRAMING = (
    "Der folgende BEWERTUNGSBOGEN stammt aus einer ANDEREN Klausur desselben "
    "Rechtsgebiets und dient nur als Qualitäts- und Strukturbeispiel. Übernimm "
    "NICHT seine Inhalte, sondern orientiere dich an seiner Struktur, der "
    "Granularität der Schritte, der konkreten Operationalisierung der "
    "Teilpunktstufen und der sauberen Herkunftskennzeichnung. Erzeuge einen "
    "eigenständigen Bewertungsbogen für das oben genannte Prüfungsmaterial."
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    FEWSHOT.mkdir(parents=True, exist_ok=True)

    # id chains
    ro = json.load(open(HERE / "data" / "processed" / "rubric_outcomes.json"))["luna"]["per_rubric"]
    sp = {p["pick_id"]: p["task_id"] for p in json.load(open(INTERIM / "picks.json"))["resolved"]}
    cp = {p["pick_id"]: p["task_id"] for p in json.load(open(INTERIM / "picks_temp0.json"))["resolved"]}
    clone2src = {cp[pid]: sp[pid] for pid in cp}
    e2l = json.load(open(INTERIM / "benchathon_local_task_map.json"))["task_id_map"]
    l2e = {v: k for k, v in e2l.items()}
    exams = {e["task_id"]: e for e in json.load(open(INTERIM / "exams.json"))}
    srcrub = {(r["task_id"], r["generator_model_id"]): r
              for r in json.load(open(HERE / "data" / "raw" / "local" / "task_rubrics.json"))
              if (r.get("generation_metadata") or {}).get("contract_version") == 3}

    # per clone exam → winner under the MAE-median filter, with full_document
    by_exam = defaultdict(list)
    for r in ro:
        by_exam[r["task_id"]].append(r)

    def exam_meta(clone_task):
        st = clone2src[clone_task]
        return exams[l2e[st]], st

    winners_by_inner = {}   # inner_id -> dict
    for ct, rows in by_exam.items():
        ex, st = exam_meta(ct)
        maes = [r["mae"] for r in rows if r["mae"] is not None]
        med = statistics.median(maes)
        elig = sorted(
            (r for r in rows if r["mae"] is not None and r["mae"] <= med
             and r["repeat_sd_mean"] is not None),
            key=lambda r: r["repeat_sd_mean"])
        cand = []
        for r in elig:
            sr = srcrub.get((st, r["generator_model_id"]))
            fd = (sr.get("generation_metadata") or {}).get("full_document") if sr else None
            fdlen = len(json.dumps(fd, ensure_ascii=False)) if fd else 10**9
            cand.append({**r, "src_task": st, "src_rubric": sr["id"] if sr else None,
                         "full_document": fd, "fd_chars": fdlen})
        winners_by_inner[ex["inner_id"]] = {"clone_task": ct, "bereich": ex["bereich"],
                                            "candidates": cand}

    # bereich rotation groups
    groups = defaultdict(list)
    for inner, w in winners_by_inner.items():
        groups[w["bereich"]].append(inner)
    for b in groups:
        groups[b].sort()

    # assign each target exam the NEXT same-bereich exam's best-eligible
    # exemplar under the 30k guard (step forward on overflow)
    assignment = {}
    for inner, w in sorted(winners_by_inner.items()):
        ring = groups[w["bereich"]]
        pos = ring.index(inner)
        chosen = None
        for step in range(1, len(ring)):
            donor_inner = ring[(pos + step) % len(ring)]
            for c in winners_by_inner[donor_inner]["candidates"]:
                if c["full_document"] and c["fd_chars"] <= MAX_EXEMPLAR_CHARS:
                    chosen = {"donor_inner": donor_inner, **c}
                    break
            if chosen:
                break
        assert chosen, f"no exemplar under {MAX_EXEMPLAR_CHARS} chars for exam {inner}"
        exemplar_text = (
            FRAMING + "\n\n<BEISPIEL_BEWERTUNGSBOGEN>\n"
            + json.dumps(chosen["full_document"], ensure_ascii=False, indent=1)
            + "\n</BEISPIEL_BEWERTUNGSBOGEN>"
        )
        assignment[inner] = {
            "target_inner": inner, "target_clone_task": w["clone_task"],
            "target_bereich": w["bereich"],
            "donor_inner": chosen["donor_inner"],
            "donor_generator": chosen["generator_model_id"],
            "donor_src_rubric": chosen["src_rubric"],
            "donor_steps": chosen["steps"], "donor_repeat_sd": chosen["repeat_sd_mean"],
            "donor_mae": chosen["mae"], "donor_fd_chars": chosen["fd_chars"],
            "exemplar_chars": len(exemplar_text), "exemplar_text": exemplar_text,
        }

    (FEWSHOT / "exemplars.json").write_text(
        json.dumps(assignment, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{'exam':>4} {'ber':4} <- {'donor':>5} {'gen':32} {'steps':>5} {'sd':>5} {'mae':>5} {'chars':>6}")
    for inner, a in sorted(assignment.items()):
        print(f"{inner:>4} {a['target_bereich'][:4]:4} <- {a['donor_inner']:>5} "
              f"{a['donor_generator'].split('/')[-1]:32} {a['donor_steps']:>5} "
              f"{a['donor_repeat_sd']:>5.2f} {a['donor_mae']:>5.1f} {a['exemplar_chars']:>6}")

    if args.dry_run:
        print("DRY RUN: no task.data writes")
        return 0

    client = Client(args.base_url)
    client.login(os.environ.get("BENGER_ADMIN_EMAIL", "admin@example.com"),
                 os.environ.get("BENGER_ADMIN_PASSWORD", "admin"))
    for inner, a in sorted(assignment.items()):
        client.request("PUT", f"/api/projects/{CLONE_PROJECT}/tasks/{a['target_clone_task']}",
                       {"data": {"exemplar_rubrics": a["exemplar_text"]}})
    # verify (read path is /api/projects/tasks/{task_id}, not nested under project)
    ok = 0
    for inner, a in sorted(assignment.items()):
        t = client.request("GET", f"/api/projects/tasks/{a['target_clone_task']}")
        got = (t.get("data") or {}).get("exemplar_rubrics") or ""
        assert got == a["exemplar_text"], f"exam {inner}: exemplar_rubrics not persisted ({len(got)} chars)"
        ok += 1
    print(f"OK: wrote + verified exemplar_rubrics on {ok}/15 clone tasks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
