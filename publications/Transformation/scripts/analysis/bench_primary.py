"""The benchmark paper's primary judge (GPT-5.4 Mini, its baseline config) per D1 pick.

The first iteration's control rows (data/interim/control_results_temp0.jsonl,
pulled from the database clone) carry a later config pass of this judge for
one pick (P01: 43 instead of 30). The benchmark's export also holds those
later passes, and its own loader filters them out by the baseline field
prefix. This helper reads the totals exactly as the benchmark does, so the
first-iteration scripts use the same single-pass values as the published
benchmark.
"""

from __future__ import annotations

import importlib.util
import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
BENCH = HERE.parent / "Benchmark_EMNLP"
RAW = BENCH / "data" / "raw" / "benchathon" / "Benchathon_export.json"
JUDGE = "gpt-5.4-mini"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def primary_totals() -> dict[str, float]:
    """pick_id -> the benchmark primary judge's single-pass raw total (45 picks)."""
    if not RAW.exists():
        raise SystemExit(f"{RAW} is missing: the benchmark's raw export is needed for the primary judge")
    ca = _load_module("bench_compute_agreement", BENCH / "scripts" / "compute_agreement.py")
    sample = json.loads((BENCH / "data" / "interim" / "benchathon_human_grading_sample.json").read_text())
    sol = {p["pick_id"]: p["subject_id"] for p in sample["picks"]}
    on_humans = ca.index_judge_on_humans(ca.load_json(RAW))
    evals = []
    for name in ("benchathon_model_evaluations.json", "benchathon_superseded_evaluations.json"):
        evals += json.loads((BENCH / "data" / "processed" / name).read_text())
    on_gens: dict[str, list[float]] = defaultdict(list)
    for r in evals:
        if r.get("raw_score") is not None:
            on_gens[r["generation_id"]].append(float(r["raw_score"]))
    out: dict[str, float] = {}
    for pid, sid in sol.items():
        j = (on_humans.get(sid) or {}).get("raw_score")
        if j is not None:
            out[pid] = float(j)
        elif len(on_gens.get(sid, [])) == 1:
            out[pid] = on_gens[sid][0]
    if len(out) != 45:
        raise SystemExit(f"benchmark primary judge: totals on {len(out)} of 45 picks")
    return out
