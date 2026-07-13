"""Derive per-system operational metadata and reproducibility facts.

Inputs (canonical task exports, same files the paper pipeline uses):
  data/raw/benchathon/Benchathon-tasks-2026-05-31.json
  data/raw/zjs/ZJS Fälle-tasks-2026-05-18.json
  data/raw/grundprinzipien/Grundprinzipien-tasks-2026-05-20.json

Output:
  data/processed/operational_metadata.json

Every number comes from the per-call ``response_metadata`` the platform logs
for each generation request (cost_usd, response_time_ms, retry_count,
created_at, temperature, max_tokens, truncated) plus a word count over
``response_content``. The ``sampling_params_observed`` block records exactly
which sampling parameters appear in the logged call metadata — parameters
absent from every call (e.g. top_p, thinking budgets) were not explicitly set
and ran at provider defaults.
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed" / "operational_metadata.json"

CORPORA = {
    "benchathon": RAW / "benchathon" / "Benchathon-tasks-2026-05-31.json",
    "zjs": RAW / "zjs" / "ZJS Fälle-tasks-2026-05-18.json",
    "grundprinzipien": RAW / "grundprinzipien" / "Grundprinzipien-tasks-2026-05-20.json",
}

# Sampling-relevant keys we check for in every logged call.
SAMPLING_KEYS = (
    "temperature", "max_tokens", "top_p", "top_k", "seed",
    "thinking_budget", "reasoning_effort", "extended_thinking",
)


def _load_tasks(path: Path):
    with open(path) as f:
        doc = json.load(f)
    return doc["tasks"] if isinstance(doc, dict) else doc


def _md(gen):
    md = gen.get("response_metadata")
    if isinstance(md, str):
        try:
            md = json.loads(md)
        except json.JSONDecodeError:
            md = {}
    return md or {}


def main():
    per_corpus = {}
    sampling_observed = defaultdict(lambda: defaultdict(set))
    run_dates = defaultdict(lambda: defaultdict(list))

    for corpus, path in CORPORA.items():
        tasks = _load_tasks(path)
        acc = defaultdict(lambda: {
            "n": 0, "costs": [], "latencies_ms": [], "words": [],
            "truncated": 0, "retries": 0,
        })
        for task in tasks:
            for gen in task.get("generations") or []:
                model = gen.get("model_id")
                if not model:
                    continue
                md = _md(gen)
                a = acc[model]
                a["n"] += 1
                if md.get("cost_usd") is not None:
                    a["costs"].append(float(md["cost_usd"]))
                if md.get("response_time_ms") is not None:
                    a["latencies_ms"].append(float(md["response_time_ms"]))
                content = gen.get("response_content") or ""
                if isinstance(content, str) and content:
                    a["words"].append(len(content.split()))
                if md.get("truncated"):
                    a["truncated"] += 1
                a["retries"] += int(md.get("retry_count") or 0)
                created = md.get("created_at") or gen.get("created_at")
                if created:
                    run_dates[corpus][model].append(created[:10])
                for key in SAMPLING_KEYS:
                    if key in md and md[key] is not None:
                        sampling_observed[model][key].add(
                            json.dumps(md[key], sort_keys=True))

        per_corpus[corpus] = {
            model: {
                "n": a["n"],
                "mean_cost_usd": (statistics.mean(a["costs"])
                                  if a["costs"] else None),
                "total_cost_usd": (round(sum(a["costs"]), 4)
                                   if a["costs"] else None),
                "n_with_cost": len(a["costs"]),
                "mean_latency_s": (statistics.mean(a["latencies_ms"]) / 1000
                                   if a["latencies_ms"] else None),
                "median_latency_s": (statistics.median(a["latencies_ms"]) / 1000
                                     if a["latencies_ms"] else None),
                "mean_words": (round(statistics.mean(a["words"]))
                               if a["words"] else None),
                "truncated": a["truncated"],
                "total_retries": a["retries"],
            }
            for model, a in sorted(acc.items())
        }

    out = {
        "_meta": {
            "description": "Per-system operational metadata from logged "
                           "per-call response_metadata; word counts from "
                           "response_content.",
            "inputs": {k: str(v.relative_to(ROOT)) for k, v in CORPORA.items()},
            "sampling_keys_checked": list(SAMPLING_KEYS),
        },
        "per_corpus": per_corpus,
        "run_date_ranges": {
            corpus: {
                model: {"first": min(dates), "last": max(dates), "n": len(dates)}
                for model, dates in sorted(models.items())
            }
            for corpus, models in run_dates.items()
        },
        "sampling_params_observed": {
            model: {
                key: sorted(json.loads(v) for v in values)
                for key, values in sorted(keys.items())
            }
            for model, keys in sorted(sampling_observed.items())
        },
    }

    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    n_models = {c: len(v) for c, v in per_corpus.items()}
    print(f"wrote {OUT.relative_to(ROOT)}: systems per corpus {n_models}")
    absent = [k for k in SAMPLING_KEYS
              if not any(k in keys for keys in sampling_observed.values())]
    print(f"sampling params never observed in any call: {absent}")


if __name__ == "__main__":
    main()
