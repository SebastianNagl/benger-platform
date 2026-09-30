#!/usr/bin/env python3
"""Generation on the expert exam (D2): compliance, attempts, failure causes, cost.

Reads the d2-generate rows (git-ignored) of the pinned validator
(d2_labels.D2_VALIDATOR, override with --validator) and writes
data/processed/cslaw/d2_generation.json: per generator the chains started,
the valid sheets, attempts per chain, the number of failed attempts and the
strict failure categories among them (an attempt can fail on several), the
categories of the last attempt of each failed chain, the
cost per chain and per valid sheet, and per valid sheet its step count, the
attempt it passed on and its soft validator hints by category. It also
copies the spend of the extended study so far (all phases, from the host
ledger data/interim/pilot/ledger.json) so the paper never carries it as a
literal.
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
sys.path[:0] = [str(HERE / "scripts"), str(HERE / "scripts" / "analysis")]
import local_config
from d2_labels import D2_VALIDATOR

DATA = Path(os.environ.get("PILOT_DATA_ROOT") or local_config.data_root())
ROWS = DATA / "interim" / "human" / "pilot" / "d2-generate.jsonl"
OUT = HERE / "data" / "processed" / "cslaw" / "d2_generation.json"
LEDGER = DATA / "interim" / "pilot" / "ledger.json"
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
    if not cats and detail:
        # not a contract error: the response itself could not be read
        cats.append("unparseable response" if "parseable" in detail or "parse" in detail.lower() else "other")
    return cats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--validator", default=D2_VALIDATOR)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    rows = [json.loads(line) for line in ROWS.read_text(encoding="utf-8").splitlines() if line.strip()]
    live = [r for r in rows if not (r.get("provenance") or {}).get("dry_run")]
    validator = args.validator
    live = [r for r in live if (r.get("provenance") or {}).get("validator_sha256") == validator]

    per = defaultdict(lambda: {"chains": 0, "valid": 0, "attempts": [], "failure_categories": Counter(),
                               "failed_attempts": 0, "final_categories": Counter(), "usd_chains": [], "sheets": []})
    for r in live:
        g = per[r["generator"]]
        g["chains"] += 1
        g["usd_chains"].append(sum(float(c.get("usd") or 0) for c in r.get("calls") or []))
        res = r.get("result") or {}
        g["attempts"].append(int(res.get("attempts") or len(r.get("attempt_errors") or []) or 0))
        for e in r.get("attempt_errors") or []:
            g["failed_attempts"] += 1
            g["failure_categories"].update(set(categories(str(e.get("detail") or ""))))
        errors = r.get("attempt_errors") or []
        if not (r.get("status") == "completed" and r.get("rubric_id")) and errors:
            # why a failed chain ended: the categories of its last attempt
            g["final_categories"].update(set(categories(str(errors[-1].get("detail") or ""))))
        if r.get("status") == "completed" and r.get("rubric_id"):
            g["valid"] += 1
            rb = r.get("rubric") or {}
            # soft validator hints by category (e.g. "gewicht": most steps above 4 BE)
            hints = Counter(m.group(1) for h in rb.get("hinweise") or [] if (m := CATEGORY.match(str(h))))
            g["sheets"].append({"steps": rb.get("steps") or res.get("steps"),
                                "attempt": rb.get("attempts") or res.get("attempts"),
                                "hints": dict(sorted(hints.items()))})
    out = {"validator_sha256": validator, "per_generator": {}}
    if LEDGER.exists():
        ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
        out["study_spend_usd"] = round(float(ledger["spent"]), 2)
        out["study_calls"] = ledger.get("calls")
    for gen, g in sorted(per.items()):
        usd = sum(g["usd_chains"])
        out["per_generator"][gen] = {
            "chains": g["chains"], "valid_sheets": g["valid"],
            "attempts_per_chain": g["attempts"],
            "failed_attempts": g["failed_attempts"],
            "failed_attempt_categories": dict(sorted(g["failure_categories"].items(), key=lambda kv: (-kv[1], kv[0]))),
            "failed_chain_final_categories": dict(sorted(g["final_categories"].items(), key=lambda kv: (-kv[1], kv[0]))),
            "usd_total": round(usd, 3),
            "usd_per_valid_sheet": round(usd / g["valid"], 3) if g["valid"] else None,
            "mean_usd_per_chain": round(statistics.fmean(g["usd_chains"]), 3) if g["usd_chains"] else None,
            "valid_sheet_steps": [s["steps"] for s in g["sheets"]],
            "valid_sheet_detail": g["sheets"],
        }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
