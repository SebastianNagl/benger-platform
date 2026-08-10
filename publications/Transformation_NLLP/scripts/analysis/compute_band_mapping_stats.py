#!/usr/bin/env python3
"""Quantify the code-side band-mapping normalizations (reviewer round 2).

The derivation step assigns integer partial-credit ranges to the model's
ordered level strings. Two operations are content-bearing and must be
reported rather than described as pure arithmetic:
  merge — more levels than available integer points (slots = max_punkte-1):
          the weakest surplus+1 levels are concatenated into the lowest band
          (logged as "… Stufen zusammengeführt");
  drop  — max_punkte == 1 leaves no band space; the levels are removed from
          the derived document (the notice text claims they are carried
          over, which is inaccurate — reported as-is).

Counts are taken from generation_metadata of the 170 contract-v3 rubrics in
data/raw/local/task_rubrics.json, cross-checked two ways: (a) the hinweise
log lines, (b) recomputing slots vs level counts from full_document.

Output: data/processed/band_mapping_stats.json
"""

from __future__ import annotations

import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
RAW = HERE / "data" / "raw" / "local" / "task_rubrics.json"
OUT = HERE / "data" / "processed" / "band_mapping_stats.json"


def iter_steps(doc):
    for sec in doc.get("abschnitte") or []:
        for st in sec.get("schritte") or []:
            yield st
    for alt in doc.get("alternative_loesungswege") or []:
        for st in alt.get("alternative_schritte") or []:
            yield st


def main() -> int:
    rubrics = json.load(open(RAW))
    v3 = [r for r in rubrics
          if (r.get("generation_metadata") or {}).get("contract_version") == 3
          and (r.get("generation_metadata") or {}).get("full_document")
          and (r.get("generation_metadata") or {}).get("derived_document")]

    n_steps = n_leveled = 0
    level_hist = {}
    merges_recomputed = drops_recomputed = 0
    merge_rubrics, drop_rubrics = set(), set()
    merged_level_losses = 0

    hin_merge = hin_drop = 0
    merge_re = re.compile(r"Stufen zusammengef")
    drop_re = re.compile(r"in die Bewertungshinweise übernommen")

    for r in v3:
        gm = r["generation_metadata"]
        full, derived = gm["full_document"], gm["derived_document"]
        d_steps = {id(st): st for st in iter_steps(derived)}
        d_list = list(iter_steps(derived))
        f_list = list(iter_steps(full))
        # full and derived documents share step order by construction
        for f_st, d_st in zip(f_list, d_list):
            n_steps += 1
            levels = [l for l in ((f_st.get("bewertungshinweise") or {})
                                  .get("teilpunktstufen") or []) if str(l).strip()]
            if not levels:
                continue
            n_leveled += 1
            level_hist[len(levels)] = level_hist.get(len(levels), 0) + 1
            maxp = d_st.get("max_punkte")
            if maxp is None:
                continue
            slots = max(maxp - 1, 0)
            if slots == 0:
                drops_recomputed += 1
                drop_rubrics.add(r["id"])
            elif len(levels) > slots:
                merges_recomputed += 1
                merge_rubrics.add(r["id"])
                merged_level_losses += len(levels) - slots
        for h in gm.get("hinweise") or []:
            text = h if isinstance(h, str) else json.dumps(h, ensure_ascii=False)
            if merge_re.search(text):
                hin_merge += 1
            if drop_re.search(text):
                hin_drop += 1

    payload = {
        "n_rubrics_v3": len(v3),
        "n_steps": n_steps,
        "n_steps_with_levels": n_leveled,
        "level_count_histogram": dict(sorted(level_hist.items())),
        "merges": {"steps": merges_recomputed, "rubrics": len(merge_rubrics),
                   "levels_lost": merged_level_losses,
                   "hinweise_log_lines": hin_merge,
                   "share_of_leveled_steps": round(merges_recomputed / n_leveled, 4)},
        "drops_at_max1": {"steps": drops_recomputed, "rubrics": len(drop_rubrics),
                          "hinweise_log_lines": hin_drop},
        "note": "merge = weakest surplus+1 level strings concatenated into the lowest "
                "band; drop = all level strings removed at max_punkte 1 (notice text "
                "inaccurately claims carry-over); recomputed from full_document vs "
                "derived_document and cross-checked against the hinweise log",
    }
    OUT.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(payload, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
