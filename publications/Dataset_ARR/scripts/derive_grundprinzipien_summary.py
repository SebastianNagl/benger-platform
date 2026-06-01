"""Derive small per-system and metric-correlation summaries from the
Grundprinzipien task export. The manuscript loads only the small outputs.

Source:
  data/raw/grundprinzipien/Grundprinzipien-tasks-2026-05-20.json

Outputs:
  data/processed/grundprinzipien_model_summary.json
    [
      {
        "system": "claude-opus-4-7",
        "n_tasks": <int>,
        "n_generations": <int>,
        "metrics": {
          "judge_raw_mean": <float, 0-100 scale>,
          "judge_pass_rate": <float>,
          "accuracy": <float, Ja/Nein exact match>,
          "<metric>_mean": <float>,   # bleu / rouge / bertscore / ...
        }
      },
      ...
    ]

  data/processed/grundprinzipien_metric_correlation.json
    {
      "<metric>": {
        "n": <int>,
        "pearson_vs_judge_raw": <float>,
        "spearman_vs_judge_raw": <float>,
      },
      ...
    }

  data/processed/grundprinzipien_tier_aggregates.json
    {
      "by_tier":     {"flagship": {"n_systems": ..., "mean_raw": ..., "min": ..., "max": ...}, ...},
      "by_weights":  {"closed":   {...}, "open": {...}},
      "by_provider": {"OpenAI":   {...}, ...}
    }

The judge here is the custom 4-dimension rubric (result_correctness 40 /
legal_knowledge 25 / subsumption 25 / clarity 10) — different from the 10-dim
Falllösung rubric used on Benchathon and ZJS. Judge raw is stored as the
normalised [0,1] score in the export; we scale * 100 so the leaderboard
shares units with the ZJS / Benchathon judge.
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _stats import pearson as _pearson  # noqa: E402
from _stats import spearman as _spearman  # noqa: E402
from _stats import welford_update as _welford_update  # noqa: E402

HERE = Path(__file__).resolve().parent.parent
SRC = HERE / "data" / "raw" / "grundprinzipien" / "grundprinzipien_Grundprinzipien_full_export.json"
# Filter judge evaluations to the GPT-5.4-mini full-corpus run (effective
# 2026-06-01). The same file also contains a legacy gpt-5-mini run under
# field-name prefix `llm_judge_custom-mpd6eyw4-...`; we ignore it.
GP_PRIMARY_JUDGE_PREFIX = "llm_judge_custom-mpu1cuad"
SYSTEMS = HERE / "data" / "processed" / "systems.json"
OUT_DIR = HERE / "data" / "processed"
OUT_SUMMARY = OUT_DIR / "grundprinzipien_model_summary.json"
OUT_CORR = OUT_DIR / "grundprinzipien_metric_correlation.json"
OUT_TIER = OUT_DIR / "grundprinzipien_tier_aggregates.json"

AUTOMATIC_METRICS = (
    "bleu", "rouge", "meteor", "chrf",
    "bertscore", "moverscore", "semantic_similarity",
)


def _running_mean_update(slot, key, value):
    if value is None:
        return
    pair = slot.setdefault(key, [0.0, 0])
    pair[0] += float(value)
    pair[1] += 1


def main() -> None:
    if not SRC.exists():
        sys.exit(f"Grundprinzipien source missing: {SRC}")

    with SRC.open("r", encoding="utf-8") as f:
        export = json.load(f)

    per_system: dict[str, dict] = defaultdict(lambda: {
        "n_generations": 0,
        "tasks": set(),
        "judge_raw": [0.0, 0],
        "judge_raw_stats": [0, 0.0, 0.0],  # Welford n, mean, M2
        "judge_pass_count": 0,
        "judge_pass_n": 0,
        "accuracy": [0.0, 0],
        "metrics": {},
    })

    per_metric_pairs: dict[str, list[tuple[float, float]]] = defaultdict(list)
    n_tasks_seen = 0
    n_gens_seen = 0

    for task in export["tasks"]:
        n_tasks_seen += 1
        task_id = task.get("id")
        for gen in task.get("generations") or []:
            mid = gen.get("model_id")
            if not mid:
                continue
            slot = per_system[mid]
            slot["n_generations"] += 1
            n_gens_seen += 1
            if task_id:
                slot["tasks"].add(task_id)

            gen_judge_raw = None
            gen_metric_vals: dict[str, float] = {}

            for ev in gen.get("evaluations") or []:
                m = ev.get("metrics") or {}
                fn = ev.get("field_name") or ""
                # Only count evals from the GPT-5.4-mini primary-judge run;
                # the legacy gpt-5-mini scoring under llm_judge_custom-mpd6eyw4
                # is ignored.
                if "llm_judge_custom" in m and not fn.startswith(GP_PRIMARY_JUDGE_PREFIX):
                    continue

                # Custom LLM judge: normalised raw in [0,1] -> scale *100
                if "raw_score" in m and "llm_judge_custom" in m:
                    raw = m.get("raw_score")
                    if raw is not None:
                        raw_100 = float(raw) * 100.0
                        _running_mean_update(slot, "judge_raw", raw_100)
                        _welford_update(slot["judge_raw_stats"], raw_100)
                        if gen_judge_raw is None:
                            gen_judge_raw = raw_100
                    passed = ev.get("passed")
                    if passed is not None:
                        slot["judge_pass_n"] += 1
                        if passed:
                            slot["judge_pass_count"] += 1
                    continue

                # Binary Ja/Nein decision (use accuracy; exact_match is a duplicate)
                if "accuracy" in m and isinstance(m["accuracy"], dict):
                    v = m["accuracy"].get("value")
                    if v is not None:
                        _running_mean_update(slot, "accuracy", v)
                    continue

                # Automatic free-text metrics
                for k in AUTOMATIC_METRICS:
                    if k in m and isinstance(m[k], dict):
                        v = m[k].get("value")
                        if v is None:
                            continue
                        _running_mean_update(slot["metrics"], k, v)
                        if k not in gen_metric_vals:
                            gen_metric_vals[k] = float(v)
                        break

            if gen_judge_raw is not None:
                for k, v in gen_metric_vals.items():
                    per_metric_pairs[k].append((v, gen_judge_raw))

    def mean(pair):
        return pair[0] / pair[1] if pair[1] else None

    import math
    rows = []
    for mid, slot in per_system.items():
        metric_means = {f"{k}_mean": mean(p) for k, p in slot["metrics"].items()}
        n_w, _, M2 = slot["judge_raw_stats"]
        raw_stdev = math.sqrt(M2 / (n_w - 1)) if n_w > 1 else None
        rows.append({
            "system": mid,
            "n_tasks": len(slot["tasks"]),
            "n_generations": slot["n_generations"],
            "metrics": {
                "judge_raw_mean": mean(slot["judge_raw"]),
                "judge_raw_stdev": raw_stdev,
                "judge_raw_n": n_w,
                "judge_pass_rate": (slot["judge_pass_count"] / slot["judge_pass_n"])
                    if slot["judge_pass_n"] else None,
                "accuracy": mean(slot["accuracy"]),
                **metric_means,
            },
        })

    rows.sort(key=lambda r: (-(r["metrics"].get("judge_raw_mean") or 0), r["system"]))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with OUT_SUMMARY.open("w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

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

    # Tier / weights / provider aggregates: mean of per-system judge means
    # (matches the ZJS aggregate convention in agreement_stats.tier_aggregates).
    systems_meta = json.loads(SYSTEMS.read_text(encoding="utf-8"))
    meta_by_id = {s["model_id"]: s for s in systems_meta}

    def _group(rows_iter, key_fn):
        out = defaultdict(list)
        for r in rows_iter:
            meta = meta_by_id.get(r["system"]) or {}
            key = key_fn(meta)
            if key is None:
                continue
            v = r["metrics"].get("judge_raw_mean")
            if v is not None:
                out[key].append(v)
        return {
            k: {
                "n_systems": len(vs),
                "mean_raw": statistics.mean(vs),
                "min": min(vs),
                "max": max(vs),
            } for k, vs in out.items()
        }

    tier_agg = {
        "by_tier":     _group(rows, lambda m: m.get("tier")),
        "by_weights":  _group(rows, lambda m: m.get("openness")),
        "by_provider": _group(rows, lambda m: m.get("provider")),
    }
    with OUT_TIER.open("w", encoding="utf-8") as f:
        json.dump(tier_agg, f, ensure_ascii=False, indent=2)

    print(
        f"wrote {OUT_SUMMARY.name} ({len(rows)} systems, "
        f"{n_tasks_seen} tasks, {n_gens_seen} gens)"
    )
    print(f"wrote {OUT_CORR.name} ({len(corr_out)} metrics)")
    print(f"wrote {OUT_TIER.name} (tier/weights/provider)")


if __name__ == "__main__":
    main()
