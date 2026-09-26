#!/usr/bin/env python3
"""Generation on the expert exam (D2): compliance, attempts, failure causes, cost.

Reads the d2-generate rows (git-ignored) of the current validator (the
provenance validator hash of the newest live row, or --validator) and writes
data/processed/cslaw/d2_generation.json: per generator the chains started,
the valid sheets, attempts per chain, the strict failure categories of every
failed attempt, the cost per chain and per valid sheet, and the shape of each
valid sheet (steps, BE range, share of steps above 4 BE, Weichenstellungen).
Aggregates only; the attempt messages quote no exam content.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
sys.path[:0] = [str(HERE / "scripts")]
import local_config  # noqa: E402

DATA = Path(os.environ.get("PILOT_DATA_ROOT") or local_config.data_root())
ROWS = DATA / "interim" / "human" / "pilot" / "d2-generate.jsonl"
OUT = HERE / "data" / "processed" / "cslaw" / "d2_generation.json"
# The prefix of a strict error names its check ("gewicht:", "weichenstellungen:" ...);
# the text after it can quote exam content, so only the category is kept.
CATEGORY = re.compile(r"^([a-zäöü_]+):")
CAP = re.compile(r"Obergrenze 10 BE")


def categories(detail: str) -> list[str]:
    cats = []
    for part in re.split(r";\s+(?=[a-zäöü_]+:)", detail or ""):
        m = CATEGORY.match(part.strip())
        if not m:
            continue
        cat = m.group(1)
        if cat == "gewicht" and CAP.search(part):
            cat = "gewicht (10 BE cap)"
        cats.append(cat)
    return cats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--validator", default=None)
    args = parser.parse_args()
    rows = [json.loads(line) for line in ROWS.read_text(encoding="utf-8").splitlines() if line.strip()]
    live = [r for r in rows if not (r.get("provenance") or {}).get("dry_run")]
    validator = args.validator or next(
        ((r.get("provenance") or {}).get("validator_sha256") for r in reversed(live)
         if (r.get("provenance") or {}).get("validator_sha256")), None)
    live = [r for r in live if (r.get("provenance") or {}).get("validator_sha256") == validator]

    per = defaultdict(lambda: {"chains": 0, "valid": 0, "attempts": [], "failure_categories": Counter(),
                               "usd_chains": [], "sheets": []})
    for r in live:
        g = per[r["generator"]]
        g["chains"] += 1
        g["usd_chains"].append(sum(float(c.get("usd") or 0) for c in r.get("calls") or []))
        res = r.get("result") or {}
        g["attempts"].append(int(res.get("attempts") or len(r.get("attempt_errors") or []) or 0))
        for e in r.get("attempt_errors") or []:
            g["failure_categories"].update(set(categories(str(e.get("detail") or ""))))
        if r.get("status") == "completed" and r.get("rubric_id"):
            g["valid"] += 1
            g["sheets"].append({"steps": (r.get("rubric") or {}).get("steps") or res.get("steps")})
    out = {"validator_sha256": validator, "per_generator": {}}
    for gen, g in sorted(per.items()):
        usd = sum(g["usd_chains"])
        out["per_generator"][gen] = {
            "chains": g["chains"], "valid_sheets": g["valid"],
            "attempts_per_chain": g["attempts"],
            "failed_attempt_categories": dict(g["failure_categories"].most_common()),
            "usd_total": round(usd, 3),
            "usd_per_valid_sheet": round(usd / g["valid"], 3) if g["valid"] else None,
            "mean_usd_per_chain": round(statistics.fmean(g["usd_chains"]), 3) if g["usd_chains"] else None,
            "valid_sheet_steps": [s["steps"] for s in g["sheets"]],
        }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
