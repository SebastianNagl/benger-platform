#!/usr/bin/env python3
"""Deterministic lexical screen of all 170 schema-conformant rubrics (WP4).

The generation prompt's rule block 8 bans indeterminate grading formulas
("Leerformeln") and partial-credit levels that differ only by degree adverbs.
The structural validator does not check this — the Appendix D example rubric
demonstrably violates it. This screen makes the gap measurable: it scans the
judge-facing rendered_text of every schema-conformant rubric for

- the prompt's five LISTED formulas (verbatim, case-insensitive),
- NEAR-VARIANT families of the same genus (documented regexes), and
- per-step partial-credit levels that collapse onto each other once degree
  adverbs (teilweise/überwiegend/weitgehend/im Wesentlichen) are removed.

A lexical hit is not automatically a semantic violation (the rule allows the
phrases when the missing performance is named concretely) — the output is a
screening statistic, labeled as such in the paper.

Input: data/raw/local/task_rubrics.json (+ sweep log for the 170-set),
       data/interim/active_rubric_selection.json (D6 draw)
Output: data/processed/rubric_screen.json
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
RUBRICS = HERE / "data" / "raw" / "local" / "task_rubrics.json"
SWEEP_LOG = HERE / "data" / "interim" / "rubric_sweep_log.jsonl"
D6 = HERE / "data" / "interim" / "active_rubric_selection.json"
OUT = HERE / "data" / "processed" / "rubric_screen.json"

LISTED = [
    "gut begründet",
    "im Wesentlichen richtig",
    "weitgehend vollständig",
    "mit kleineren Fehlern",
    "vertretbare Ausführungen",
]

NEAR_VARIANTS = {
    "im_wesentlichen_x": r"im wesentlichen (?:zutreffend|korrekt|erfasst|vollständig|erkannt)",
    "kleinere_x": r"kleinere[nr]? (?:unschärfen|fehler|mängel|ungenauigkeiten|lücken|schwächen)",
    "weitgehend_x": r"weitgehend (?:richtig|korrekt|zutreffend|erfasst)",
    "ueberwiegend_x": r"überwiegend (?:richtig|korrekt|zutreffend|vollständig)",
}

DEGREE_ADVERBS = r"(?:teilweise|überwiegend|weitgehend|im wesentlichen)"
LEVEL_LINE = re.compile(r"^\s*(?:volle punkte|keine punkte|[0-9][0-9,.\s–\-]*punkte?)\s*(?:\([^)]*\))?\s*:\s*(.+)$")


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFC", s).lower()
    return re.sub(r"\s+", " ", s)


def _level_texts(step_rubric: str):
    for line in step_rubric.splitlines():
        m = LEVEL_LINE.match(_norm(line))
        if m:
            yield m.group(1)


def main() -> int:
    # Completed sweep series carry a rubric_id; failures never create DB rows
    # (and no rubric_id in the log). 170 of the 220 series completed.
    rubric_ids = set()
    for line in SWEEP_LOG.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r.get("rubric_id"):
            rubric_ids.add(r["rubric_id"])
    d6_ids = {r["rubric_id"] for r in json.loads(D6.read_text())["selection"]}
    assert d6_ids <= rubric_ids, "D6 draw not a subset of the sweep's rubrics"

    rows = [r for r in json.loads(RUBRICS.read_text()) if r["id"] in rubric_ids]
    assert len(rows) == len(rubric_ids), (
        f"snapshot covers {len(rows)}/{len(rubric_ids)} sweep rubrics — re-pull sidecar")

    listed_pat = {p: re.compile(re.escape(_norm(p))) for p in LISTED}
    near_pat = {k: re.compile(v) for k, v in NEAR_VARIANTS.items()}

    per_rubric = []
    per_gen = defaultdict(lambda: {"n": 0, "listed_hit": 0, "near_hit": 0,
                                   "degree_hit": 0, "any_hit": 0})
    phrase_totals, near_totals = Counter(), Counter()
    for r in sorted(rows, key=lambda x: x["id"]):
        text = _norm((r.get("generation_metadata") or {}).get("rendered_text") or "")
        assert text, f"rubric {r['id']} has no rendered_text"
        listed_hits = {p: len(pat.findall(text)) for p, pat in listed_pat.items()}
        listed_hits = {p: n for p, n in listed_hits.items() if n}
        near_hits = {}
        for key, pat in near_pat.items():
            # Count near-variant matches that are not already a listed match.
            n = 0
            for m in pat.finditer(text):
                if not any(lp.search(text, max(0, m.start() - 6), m.end() + 6)
                           for lp in listed_pat.values()):
                    n += 1
            if n:
                near_hits[key] = n

        crit = r["criteria"]
        if isinstance(crit, str):
            crit = json.loads(crit)
        degree_steps = []
        for step_key, step in crit.items():
            if not isinstance(step, dict):
                continue
            levels = list(_level_texts(step.get("rubric") or ""))
            stripped = [re.sub(r"\s+", " ", re.sub(DEGREE_ADVERBS, "", lv)).strip(" .,;")
                        for lv in levels]
            seen = {}
            for lv, sv in zip(levels, stripped):
                if sv and sv in seen and seen[sv] != lv:
                    degree_steps.append(step_key)
                    break
                seen.setdefault(sv, lv)

        gen = r.get("generator_model_id")
        g = per_gen[gen]
        g["n"] += 1
        g["listed_hit"] += bool(listed_hits)
        g["near_hit"] += bool(near_hits)
        g["degree_hit"] += bool(degree_steps)
        g["any_hit"] += bool(listed_hits or near_hits or degree_steps)
        phrase_totals.update(listed_hits)
        near_totals.update(near_hits)
        per_rubric.append({
            "rubric_id": r["id"],
            "task_id": r["task_id"],
            "generator_model_id": gen,
            "d6_active": r["id"] in d6_ids,
            "listed": listed_hits,
            "near_variants": near_hits,
            "degree_only_level_steps": degree_steps,
        })

    def _agg(pred):
        return sum(1 for x in per_rubric if pred(x))

    payload = {
        "definitions": {
            "listed_formulas": LISTED,
            "near_variant_patterns": NEAR_VARIANTS,
            "degree_only_levels": "two partial-credit levels of one step become identical "
                                  "after removing teilweise/überwiegend/weitgehend/im Wesentlichen",
            "note": "lexical screening over the judge-facing rendered_text; a hit is not "
                    "automatically a semantic violation (the prompt allows the phrases when "
                    "the missing performance is named concretely)",
        },
        "n_rubrics": len(per_rubric),
        "listed": {"n_rubrics_hit": _agg(lambda x: x["listed"]),
                   "occurrences": sum(phrase_totals.values()),
                   "per_phrase": dict(phrase_totals)},
        "near_variants": {"n_rubrics_hit": _agg(lambda x: x["near_variants"]),
                          "occurrences": sum(near_totals.values()),
                          "per_family": dict(near_totals)},
        "degree_only_levels": {"n_rubrics_hit": _agg(lambda x: x["degree_only_level_steps"]),
                               "n_steps_hit": sum(len(x["degree_only_level_steps"]) for x in per_rubric)},
        "any": {"n_rubrics_hit": _agg(lambda x: x["listed"] or x["near_variants"]
                                      or x["degree_only_level_steps"])},
        "d6_active": {
            "n": len(d6_ids),
            "listed_hit": _agg(lambda x: x["d6_active"] and x["listed"]),
            "any_hit": _agg(lambda x: x["d6_active"] and (x["listed"] or x["near_variants"]
                                                          or x["degree_only_level_steps"])),
        },
        "per_generator": dict(sorted(per_gen.items())),
        "per_rubric": per_rubric,
    }
    OUT.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{payload['n_rubrics']} rubrics screened -> {OUT.name}")
    print(f"listed formulas: {payload['listed']['n_rubrics_hit']} rubrics, "
          f"{payload['listed']['occurrences']} occurrences {dict(phrase_totals)}")
    print(f"near variants:   {payload['near_variants']['n_rubrics_hit']} rubrics, "
          f"{payload['near_variants']['occurrences']} occurrences {dict(near_totals)}")
    print(f"degree-only levels: {payload['degree_only_levels']['n_rubrics_hit']} rubrics / "
          f"{payload['degree_only_levels']['n_steps_hit']} steps")
    print(f"any signal: {payload['any']['n_rubrics_hit']}/{payload['n_rubrics']}; "
          f"D6 actives: {payload['d6_active']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
