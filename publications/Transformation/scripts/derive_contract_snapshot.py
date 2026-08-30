#!/usr/bin/env python3
"""Snapshot the code-owned rubric-generation contract for the manuscript.

Loads ``bewertungsbogen_constants`` (v2) from the benger-extended checkout by
file path (the module is stdlib-only) and writes the contract version,
structural constants, enums, the fixed format-contract suffix and the system
suffix to ``data/processed/rubric_contract.json``. Appendix A renders from
that file, so the paper can never drift from the implementation.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
CONSTANTS = (
    HERE.parent.parent.parent
    / "benger-extended"
    / "benger_extended"
    / "workers"
    / "bewertungsbogen_constants.py"
)
OUT = HERE / "data" / "processed" / "rubric_contract.json"


def main() -> int:
    spec = importlib.util.spec_from_file_location("bewertungsbogen_constants", CONSTANTS)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    snapshot = {
        "source": str(CONSTANTS),
        "contract_version": mod.CONTRACT_VERSION,
        "bounds": {
            "total_points": mod.TOTAL_POINTS,
            "min_points_per_step": mod.MIN_POINTS_PER_STEP,
            "textanker_soft_max_words": mod.TEXTANKER_SOFT_MAX_WORDS,
            "step_key_pattern": mod.STEP_KEY_PATTERN.pattern,
        },
        "enums": {
            "gewichtungsklassen": list(mod.GEWICHTUNGSKLASSEN),
            "herkunft": list(mod.HERKUNFT_WERTE),
            "ergaenzungstypen": list(mod.ERGAENZUNGSTYPEN),
            "alternative_typen": list(mod.ALT_TYPEN),
            "warnung_typen": list(mod.WARNUNG_TYPEN),
        },
        "validation": (
            "two-tier: STRICT fails the attempt (structure incl. leading "
            "vorueberlegung field; integer relative weights >= 1; globally "
            "unique IDs A*/SP*/S*/ALT*/ALT*-S*; scoring-relevant "
            "cross-references resolve, with admissible values named in the "
            "error; provenance rules — Fundstelle for explizit/implizit, "
            "Begründung for extern; declared Schwerpunkte non-empty); SOFT "
            "is logged, never fails (Textanker length guideline, dangling "
            "refs in non-scoring fields, unknown warning types). The model "
            "states no derived number: code apportions 100 points over "
            "step weights (largest remainder, floor 1), derives section/"
            "Schwerpunkt totals and ALT budgets, and assigns partial-credit "
            "level ranges."
        ),
        "harness": (
            "plain text generation (identical for every provider — no "
            "native structured-output APIs), 3-stage JSON parser + bounded "
            "encoding-only repair pass (logged), 3 attempts per series with "
            "validator-feedback on attempts 2-3 (attempt 1 feedback-free), "
            "max_tokens 32000 (Anthropic via streaming)"
        ),
        "format_contract_suffix": mod.FORMAT_CONTRACT,
        "system_prompt_suffix": mod.SYSTEM_PROMPT_SUFFIX,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUT.relative_to(HERE)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
