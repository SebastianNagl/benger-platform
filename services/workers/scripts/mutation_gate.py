#!/usr/bin/env python3
"""Mutation-score gate — the co-gate for the coverage ratchet.

Parses a mutmut junit-xml report, computes the mutation score for one module,
and enforces its floor from mutation-floors.cfg. Always prints a table (score,
floor, delta, suggested bump) so a passing run still shows headroom; exits
non-zero only on a real regression below floor.

Usage (run after `mutmut run` for a single module):
    mutmut junitxml > mutmut.xml
    python scripts/mutation_gate.py --junitxml mutmut.xml \
        --module ml_evaluation/statistics.py --floors mutation-floors.cfg

Mutation score = killed / (killed + survived); timeouts/suspicious (junit
<error>) are excluded from the denominator, matching the Stryker convention.
"""
from __future__ import annotations

import argparse
import configparser
import math
import sys
import xml.etree.ElementTree as ET


def _parse_junit(path: str) -> tuple[int, int, int]:
    """Return (total, survived, errored) from a mutmut junit-xml report.

    mutmut emits one <testcase> per mutant; a surviving mutant is a <failure>,
    a timeout/suspicious mutant is an <error>.
    """
    root = ET.parse(path).getroot()
    # Handle both <testsuite> root and <testsuites> wrapper.
    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
    total = survived = errored = 0
    for suite in suites:
        for case in suite.findall("testcase"):
            total += 1
            if case.find("failure") is not None:
                survived += 1
            elif case.find("error") is not None:
                errored += 1
    return total, survived, errored


def _load_floor(floors_path: str, module: str) -> int:
    cfg = configparser.ConfigParser()
    cfg.read(floors_path)
    if not cfg.has_section("floors"):
        return 0
    # configparser lowercases keys by default; match case-insensitively.
    for key, val in cfg.items("floors"):
        if key.strip() == module.strip().lower() or key.strip() == module.strip():
            try:
                return int(val)
            except ValueError:
                return 0
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--junitxml", required=True)
    ap.add_argument("--module", required=True)
    ap.add_argument("--floors", required=True)
    args = ap.parse_args()

    total, survived, errored = _parse_junit(args.junitxml)
    denom = total - errored  # killed + survived
    killed = denom - survived
    score = (killed / denom * 100.0) if denom else 100.0
    floor = _load_floor(args.floors, args.module)

    ok = score + 1e-9 >= floor
    status = "PASS" if ok else "FAIL"
    print("─" * 64)
    print(f"Mutation gate [{status}] — {args.module}")
    print(f"  mutants:  {total}  (killed {killed}, survived {survived}, "
          f"timeout/suspicious {errored})")
    print(f"  score:    {score:.2f}%   floor: {floor}%   "
          f"delta: {score - floor:+.2f}")
    print(f"  ratchet:  suggested floor = {math.floor(score)} "
          f"(set in {args.floors} if it went up)")
    print("─" * 64)
    if not ok:
        print(
            f"::error::mutation score {score:.2f}% for {args.module} is below "
            f"floor {floor}% — a test was weakened or new code lacks a killing "
            f"assertion. Strengthen the tests (don't lower the floor).",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
