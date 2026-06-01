"""Stream-derive a small per-system ZJS summary from the 3.6 GB ZJS task export.

The full export is too large to load with json.load on a normal laptop,
so we stream `tasks.item` with ijson and only keep per-(system, metric)
running aggregates. Output is a single small JSON file the manuscript loads.

Source:
  data/raw/zjs/ZJS Fälle-tasks-2026-05-18.json

Output:
  data/processed/zjs_model_summary.json
    [
      {
        "system": "claude-opus-4-7",
        "n_tasks": <int>,
        "n_generations": <int>,
        "metrics": {
          "llm_judge_falloesung_raw_mean": <float>,
          "grade_points_mean": <float>,
          "pass_rate": <float>,
          "<metric>_mean": <float>,   # bleu / rouge / bertscore / ...
          ...
        }
      },
      ...
    ]

Idempotent. Reads ~3.6 GB sequentially; runs in a few minutes.
"""

from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import ijson

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _stats import pearson as _pearson  # noqa: E402
from _stats import spearman as _spearman  # noqa: E402

HERE = Path(__file__).resolve().parent.parent
SRC = HERE / "data" / "raw" / "zjs" / "zjs_faelle_full_export.json"
# Filter judge evaluations to the GPT-5.4-mini full-corpus run (effective
# 2026-06-01). The same file also contains a legacy gpt-5-nano run under
# field-name prefix `llm_judge_falloesung-mp3ud0rq-...`; we ignore it.
ZJS_PRIMARY_JUDGE_PREFIX = "llm_judge_falloesung-mptrd45m"
OUT = HERE / "data" / "processed" / "zjs_model_summary.json"
OUT_CORR = HERE / "data" / "processed" / "zjs_metric_correlation.json"

AUTOMATIC_METRICS = (
    "bleu", "rouge", "meteor",
    "bertscore", "moverscore", "semantic_similarity",
    "coherence",
)


def _coerce_number(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        for k in ("value", "score", "raw_score", "mean"):
            if k in value:
                return _coerce_number(value[k])
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _running_mean_update(slot, key, value):
    v = _coerce_number(value)
    if v is None:
        return
    pair = slot.setdefault(key, [0.0, 0])
    pair[0] += v
    pair[1] += 1


def _welford_update(stats, value):
    """Online (n, mean, M2) update; sample variance is M2/(n-1).

    Kept local because it pre-coerces via `_coerce_number` to handle the
    nested-dict shapes the ZJS judge export produces (e.g. {"value": 0.8}).
    One-pass over the multi-GB ZJS stream — no per-gen buffer needed.
    """
    v = _coerce_number(value)
    if v is None:
        return
    stats[0] += 1
    delta = v - stats[1]
    stats[1] += delta / stats[0]
    stats[2] += delta * (v - stats[1])


def main() -> None:
    if not SRC.exists():
        sys.exit(f"ZJS source missing: {SRC}")

    per_system: dict[str, dict] = defaultdict(lambda: {
        "n_generations": 0,
        "tasks": set(),
        "raw_score": [0.0, 0],
        "raw_score_stats": [0, 0.0, 0.0],  # Welford n, mean, M2
        "grade_points": [0.0, 0],
        "pass_count": 0,
        "pass_n": 0,
        "metrics": {},
    })

    t0 = time.time()
    n_tasks_seen = 0
    n_gens_seen = 0
    n_evals_seen = 0

    # Per-generation accumulator: gather judge_raw and each metric value across
    # the multiple evaluation rows on the same gen, then emit (metric_value,
    # judge_raw) pairs per metric for RQ3 correlation analysis at the end.
    per_metric_pairs: dict[str, list[tuple[float, float]]] = defaultdict(list)

    with SRC.open("rb") as f:
        for task in ijson.items(f, "tasks.item"):
            n_tasks_seen += 1
            task_id = task.get("id")
            for gen in task.get("generations") or []:
                mid = gen.get("model_id")
                if not mid:
                    continue
                slot = per_system[mid]
                slot["n_generations"] += 1
                if task_id:
                    slot["tasks"].add(task_id)
                n_gens_seen += 1

                # First pass over this gen's evaluations: collect the judge
                # raw score and any automatic-metric values into a per-gen
                # dict so they can be paired (they live in separate eval rows).
                gen_judge_raw = None
                gen_metric_vals: dict[str, float] = {}
                for ev in gen.get("evaluations") or []:
                    n_evals_seen += 1
                    fn = ev.get("field_name") or ""
                    # Only count evals from the GPT-5.4-mini primary-judge run;
                    # skip the legacy gpt-5-nano scoring also present in this file.
                    is_judge_ev = "llm_judge_falloesung" in (ev.get("metrics") or {})
                    is_primary_judge = fn.startswith(ZJS_PRIMARY_JUDGE_PREFIX)
                    m = ev.get("metrics") or {}
                    if "llm_judge_falloesung" in m and is_primary_judge:
                        judge = m["llm_judge_falloesung"]
                        details = judge.get("details") if isinstance(judge, dict) else None
                        raw = (details or {}).get("raw_score") if details else None
                        if raw is None:
                            raw = m.get("raw_score")
                        if raw is None and isinstance(judge, (int, float)):
                            raw = judge * 100.0
                        _running_mean_update(slot, "raw_score", raw)
                        _welford_update(slot["raw_score_stats"], raw)

                        gp = (details or {}).get("grade_points") if details else None
                        if gp is None:
                            gp = m.get("llm_judge_falloesung_grade_points")
                        _running_mean_update(slot, "grade_points", gp)

                        passed = (details or {}).get("passed") if details else None
                        if passed is None:
                            passed = m.get("llm_judge_falloesung_passed")
                        if passed is not None:
                            slot["pass_n"] += 1
                            if passed:
                                slot["pass_count"] += 1

                        if gen_judge_raw is None:
                            n = _coerce_number(raw)
                            if n is not None:
                                gen_judge_raw = n
                    for k in AUTOMATIC_METRICS:
                        if k in m:
                            v = m[k]
                            if isinstance(v, dict):
                                v = v.get("value", v.get("score"))
                            _running_mean_update(slot["metrics"], k, v)
                            n = _coerce_number(v)
                            if n is not None and k not in gen_metric_vals:
                                gen_metric_vals[k] = n

                if gen_judge_raw is not None:
                    for k, v in gen_metric_vals.items():
                        per_metric_pairs[k].append((v, gen_judge_raw))

            if n_tasks_seen % 50 == 0:
                elapsed = time.time() - t0
                print(
                    f"  ... {n_tasks_seen} tasks, {n_gens_seen} gens, "
                    f"{n_evals_seen} evals in {elapsed:.1f}s",
                    file=sys.stderr,
                )

    import math
    rows = []
    for mid, slot in per_system.items():
        def mean(pair):
            return pair[0] / pair[1] if pair[1] else None

        metric_means = {
            f"{k}_mean": mean(pair)
            for k, pair in slot["metrics"].items()
        }
        n_w, _, M2 = slot["raw_score_stats"]
        raw_stdev = math.sqrt(M2 / (n_w - 1)) if n_w > 1 else None
        rows.append({
            "system": mid,
            "n_tasks": len(slot["tasks"]),
            "n_generations": slot["n_generations"],
            "metrics": {
                "llm_judge_falloesung_raw_mean": mean(slot["raw_score"]),
                "llm_judge_falloesung_raw_stdev": raw_stdev,
                "llm_judge_falloesung_raw_n": n_w,
                "grade_points_mean": mean(slot["grade_points"]),
                "pass_rate": (slot["pass_count"] / slot["pass_n"]) if slot["pass_n"] else None,
                **metric_means,
            },
        })

    rows.sort(key=lambda r: (-(r["metrics"].get("grade_points_mean") or 0), r["system"]))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    # Per-generation Pearson / Spearman of each automatic metric against the
    # LLM-judge raw score across the full ZJS corpus (n much larger than the
    # Benchathon subset, so the correlations are tighter statistical estimates).
    corr_out = {}
    for metric, pairs in per_metric_pairs.items():
        xs = [p[0] for p in pairs]
        ys = [p[1] for p in pairs]
        corr_out[metric] = {
            "n": len(pairs),
            "pearson_vs_judge_raw": _pearson(xs, ys),
            "spearman_vs_judge_raw": _spearman(xs, ys),
        }
    with OUT_CORR.open("w", encoding="utf-8") as f:
        json.dump(corr_out, f, ensure_ascii=False, indent=2)

    elapsed = time.time() - t0
    print(
        f"wrote {OUT.name} ({len(rows)} systems, {n_tasks_seen} tasks, "
        f"{n_gens_seen} gens, {n_evals_seen} evals) in {elapsed:.1f}s"
    )
    print(f"wrote {OUT_CORR.name} ({len(corr_out)} metrics)")


if __name__ == "__main__":
    main()
