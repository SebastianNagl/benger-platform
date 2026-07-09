"""Reasoning-core robustness check: leaderboard without the form dimensions.

Reviewer question: does the benchmark measure subsumption-based legal
reasoning, or is the ranking driven by the three form dimensions
(Gliederung 5, Sprache 3, Formalia 2 — 10/100 rubric points)? To answer,
we recompute the per-system leaderboard using ONLY the seven reasoning-core
dimensions (90/100 points), rescaled to /100 via core_sum / 90 * 100, and
report Spearman/Kendall rank agreement with the full-rubric ranking.

Sources (read-only):
  - data/raw/benchathon/Benchathon_export.json
      Baseline single-pass primary judge (BASELINE_JUDGE_FIELD_PREFIX from
      derive_paper_exports.py, i.e. llm_judge_falloesung-mptmfvee-sqyx),
      per-dimension scores nested in the judge evaluation payload.
  - data/raw/zjs/zjs_faelle_full_export.json (streamed with ijson)
      GPT-5.4-mini full-corpus primary run (ZJS_PRIMARY_JUDGE_PREFIX from
      derive_zjs_summary.py, i.e. llm_judge_falloesung-mptrd45m).

Grundprinzipien (Doctrinal Principles) is EXCLUDED: it uses a different
4-dimension rubric, so the 7-vs-10 dimension split does not apply.

Output:
  data/processed/reasoning_core_leaderboard.json
    {
      "_meta": {...},                       # prefixes, weights, sanity checks
      "benchathon": {system: {"n", "mean_full", "mean_core"}, ...},
      "zjs":        {system: {"n", "mean_full", "mean_core"}, ...},
      "rank_agreement": {corpus: {"spearman_rho", "kendall_tau", "n_systems"}}
    }

One score per generation: within each corpus the first primary-prefix judge
row per generation_id is used (mirroring derive_paper_exports.py's
prefix-filtered per-generation extraction); any further primary-prefix rows
on the same generation are counted and skipped. Generations missing the raw
score or any of the seven core dimensions are excluded from BOTH means so
mean_full and mean_core are computed over the identical generation set.

Idempotent: rerunning overwrites the output deterministically.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import ijson

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _stats import kendall_tau, spearman  # noqa: E402
from derive_paper_exports import (  # noqa: E402
    BASELINE_JUDGE_FIELD_PREFIX,
    _baseline_judge_score,
    _zjs_model_whitelist,
    canonical_model_id,
    iter_gen_evals,
    load,
)
from derive_zjs_summary import SRC as ZJS_SRC  # noqa: E402
from derive_zjs_summary import ZJS_PRIMARY_JUDGE_PREFIX  # noqa: E402

HERE = Path(__file__).resolve().parent.parent
BENCHATHON_EXPORT = HERE / "data" / "raw" / "benchathon" / "Benchathon_export.json"
OUT = HERE / "data" / "processed" / "reasoning_core_leaderboard.json"

# 10-dimension Falllösung rubric weights (= max points per dimension, sum 100).
RUBRIC_WEIGHTS = {
    "ergebnisrichtigkeit": 20,
    "vollstaendigkeit": 10,
    "rechtsgrundlagen": 10,
    "rechtskenntnis": 15,
    "subsumtion": 15,
    "schwerpunktsetzung": 10,
    "methodischer_stil": 10,
    "gliederung": 5,
    "sprache": 3,
    "formalia": 2,
}
FORM_DIMS = ("gliederung", "sprache", "formalia")           # 10/100, grade form
CORE_DIMS = tuple(d for d in RUBRIC_WEIGHTS if d not in FORM_DIMS)  # 90/100
CORE_MAX = float(sum(RUBRIC_WEIGHTS[d] for d in CORE_DIMS))  # 90.0


def _dims_payload(metrics: dict) -> dict:
    """Return the raw judge `dimensions` dict ({name: {score, max, ...}}).

    Mirrors the source-priority chain of derive_paper_exports's
    _baseline_judge_score, but keeps the full per-dimension payload so the
    declared `max` field can be checked against RUBRIC_WEIGHTS.
    """
    m = metrics or {}
    kf = m.get("llm_judge_falloesung")
    if isinstance(kf, dict):
        details = kf.get("details") or {}
        for src in (
            (details.get("judge_response") or {}).get("dimensions"),
            (kf.get("judge_response") or {}).get("dimensions"),
            details.get("dimensions"),
        ):
            if isinstance(src, dict) and src:
                return src
    response = m.get("llm_judge_falloesung_response") or {}
    details_blob = m.get("llm_judge_falloesung_details") or {}
    for src in (
        response.get("dimensions") if isinstance(response, dict) else None,
        details_blob.get("dimensions") if isinstance(details_blob, dict) else None,
    ):
        if isinstance(src, dict) and src:
            return src
    return {}


class _CorpusAccumulator:
    """Per-system running sums plus per-dimension sanity stats."""

    def __init__(self, primary_prefix: str):
        self.primary_prefix = primary_prefix
        self.per_system = defaultdict(lambda: {"n": 0, "sum_full": 0.0, "sum_core": 0.0})
        self.dim_sanity: dict[str, dict] = {}
        self.counters = defaultdict(int)
        # |sum(10 dims) - raw_score| accumulator (consistency of the rubric total)
        self._dimsum_absdiff = [0.0, 0]

    def _update_sanity(self, dims_payload: dict) -> None:
        for name, info in dims_payload.items():
            if not isinstance(info, dict):
                continue
            score = info.get("score")
            if score is None:
                continue
            s = float(score)
            slot = self.dim_sanity.setdefault(name, {
                "weight": RUBRIC_WEIGHTS.get(name),
                "declared_max": None,
                "observed_max": s,
                "observed_min": s,
                "n": 0,
            })
            slot["n"] += 1
            slot["observed_max"] = max(slot["observed_max"], s)
            slot["observed_min"] = min(slot["observed_min"], s)
            declared = info.get("max")
            if declared is not None:
                declared = float(declared)
                slot["declared_max"] = (declared if slot["declared_max"] is None
                                        else max(slot["declared_max"], declared))

    def add(self, system: str, ev_metrics: dict) -> None:
        """Consume one (deduplicated) primary-judge evaluation row."""
        raw, _gp, _passed, dims = _baseline_judge_score(ev_metrics)
        self._update_sanity(_dims_payload(ev_metrics))
        if raw is None:
            self.counters["skipped_missing_raw_score"] += 1
            return
        raw = float(raw)
        if any(d not in dims for d in CORE_DIMS):
            self.counters["skipped_missing_core_dimension"] += 1
            return
        core = sum(dims[d] for d in CORE_DIMS) / CORE_MAX * 100.0
        slot = self.per_system[system]
        slot["n"] += 1
        slot["sum_full"] += raw
        slot["sum_core"] += core
        if all(d in dims for d in RUBRIC_WEIGHTS):
            self._dimsum_absdiff[0] += abs(sum(dims[d] for d in RUBRIC_WEIGHTS) - raw)
            self._dimsum_absdiff[1] += 1

    def rows(self) -> dict[str, dict]:
        out = {
            system: {
                "n": s["n"],
                "mean_full": s["sum_full"] / s["n"],
                "mean_core": s["sum_core"] / s["n"],
            }
            for system, s in self.per_system.items() if s["n"]
        }
        return dict(sorted(out.items(), key=lambda kv: -kv[1]["mean_full"]))

    def meta(self) -> dict:
        total, n = self._dimsum_absdiff
        return {
            "primary_judge_prefix": self.primary_prefix,
            "counters": dict(self.counters),
            "dimension_sanity": {
                d: self.dim_sanity[d] for d in RUBRIC_WEIGHTS if d in self.dim_sanity
            },
            "mean_abs_diff_dimsum_vs_raw_score": (total / n) if n else None,
        }


def collect_benchathon() -> _CorpusAccumulator:
    acc = _CorpusAccumulator(BASELINE_JUDGE_FIELD_PREFIX)
    export = load(BENCHATHON_EXPORT)
    whitelist = _zjs_model_whitelist()
    seen_gens: set[str] = set()
    for _task_id, gen, ev in iter_gen_evals(export):
        if not str(ev.get("field_name") or "").startswith(BASELINE_JUDGE_FIELD_PREFIX):
            continue
        mid = canonical_model_id(gen["model_id"])
        if whitelist is not None and mid not in whitelist:
            acc.counters["skipped_not_in_canonical_model_set"] += 1
            continue
        gid = gen["id"]
        if gid in seen_gens:
            acc.counters["duplicate_primary_judge_rows_skipped"] += 1
            continue
        seen_gens.add(gid)
        acc.add(mid, ev.get("metrics"))
    return acc


def collect_zjs() -> _CorpusAccumulator:
    acc = _CorpusAccumulator(ZJS_PRIMARY_JUDGE_PREFIX)
    if not ZJS_SRC.exists():
        sys.exit(f"ZJS source missing: {ZJS_SRC}")
    seen_gens: set[str] = set()
    n_tasks = 0
    with ZJS_SRC.open("rb") as f:
        for task in ijson.items(f, "tasks.item"):
            n_tasks += 1
            for gen in task.get("generations") or []:
                mid = gen.get("model_id")
                if not mid:
                    continue
                for ev in gen.get("evaluations") or []:
                    fn = ev.get("field_name") or ""
                    if not fn.startswith(ZJS_PRIMARY_JUDGE_PREFIX):
                        continue
                    gid = gen.get("id")
                    if gid in seen_gens:
                        acc.counters["duplicate_primary_judge_rows_skipped"] += 1
                        continue
                    seen_gens.add(gid)
                    acc.add(canonical_model_id(mid), ev.get("metrics"))
            if n_tasks % 100 == 0:
                print(f"  ... zjs: {n_tasks} tasks streamed", file=sys.stderr)
    return acc


def _rank_agreement(rows: dict[str, dict]) -> dict:
    systems = sorted(rows)
    fulls = [rows[s]["mean_full"] for s in systems]
    cores = [rows[s]["mean_core"] for s in systems]
    return {
        "spearman_rho": spearman(fulls, cores),
        "kendall_tau": kendall_tau(fulls, cores),
        "n_systems": len(systems),
    }


def main() -> None:
    print("Collecting Benchathon (primary judge "
          f"{BASELINE_JUDGE_FIELD_PREFIX}) ...")
    bench = collect_benchathon()
    print("Collecting ZJS (primary judge "
          f"{ZJS_PRIMARY_JUDGE_PREFIX}; streaming, takes minutes) ...")
    zjs = collect_zjs()

    bench_rows = bench.rows()
    zjs_rows = zjs.rows()

    payload = {
        "_meta": {
            "description": (
                "Robustness check: per-system leaderboard recomputed on the "
                "seven reasoning-core rubric dimensions only (90/100 points), "
                "rescaled to /100 as core_sum / 90 * 100, vs. the full-rubric "
                "raw score. One primary-judge score per generation."
            ),
            "rubric_weights": RUBRIC_WEIGHTS,
            "core_dimensions": list(CORE_DIMS),
            "form_dimensions": list(FORM_DIMS),
            "core_max_points": CORE_MAX,
            "rescale": "mean_core = mean over generations of core_sum / 90 * 100",
            "exclusions": {
                "grundprinzipien": (
                    "excluded — Doctrinal Principles uses a different "
                    "4-dimension rubric; the 7-core / 3-form split of the "
                    "Falllösung rubric does not apply"
                ),
                "benchathon_model_filter": (
                    "restricted to the canonical ZJS model set "
                    "(zjs_model_summary.json), matching derive_paper_exports.py"
                ),
                "generation_filter": (
                    "generations missing the raw score or any of the seven "
                    "core dimensions are excluded from both means; see "
                    "per-corpus counters"
                ),
            },
            "benchathon": bench.meta(),
            "zjs": zjs.meta(),
        },
        "benchathon": bench_rows,
        "zjs": zjs_rows,
        "rank_agreement": {
            "benchathon": _rank_agreement(bench_rows),
            "zjs": _rank_agreement(zjs_rows),
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"wrote {OUT.relative_to(HERE)}")

    for corpus, rows in (("benchathon", bench_rows), ("zjs", zjs_rows)):
        ra = payload["rank_agreement"][corpus]
        print(f"\n{corpus}: {ra['n_systems']} systems, "
              f"rho={ra['spearman_rho']}, tau={ra['kendall_tau']}")
        rank_core = {s: i for i, (s, _) in enumerate(
            sorted(rows.items(), key=lambda kv: -kv[1]["mean_core"]), start=1)}
        for i, (s, r) in enumerate(rows.items(), start=1):
            print(f"  full#{i:>2} core#{rank_core[s]:>2}  "
                  f"full={r['mean_full']:6.2f} core={r['mean_core']:6.2f} "
                  f"n={r['n']:<4} {s}")


if __name__ == "__main__":
    main()
