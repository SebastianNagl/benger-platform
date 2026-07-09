"""Derive the paired Thinking-vs-Instruct reasoning-mode ablation table.

Pairs Qwen3-235B-A22B-Thinking-2507 (main evaluation) against
Qwen3-235B-A22B-Instruct-2507 (ablation sidecar) on Benchathon and
Doctrinal Principles under the identical pipeline and primary judge.

Inputs:
  data/raw/benchathon/Benchathon-tasks-2026-05-31.json   (Thinking judge rows)
  data/processed/grundprinzipien_model_summary.json       (Thinking GP stats)
  data/processed/operational_metadata.json                (Thinking ops)
  data/raw/ablation/qwen_instruct_ablation.json           (Instruct, sidecar)

Output:
  data/processed/reasoning_ablation.json
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
OUT = PROCESSED / "reasoning_ablation.json"

THINKING = "Qwen/Qwen3-235B-A22B-Thinking-2507"
INSTRUCT = "Qwen/Qwen3-235B-A22B-Instruct-2507"
BENCH_PRIMARY_PREFIX = "llm_judge_falloesung-mptmfvee"
PASS_RAW = 50.0


def _load(path):
    with open(path) as f:
        return json.load(f)


def _judge_raw_from_metrics(metrics):
    """Extract (raw_score, passed) from a judge evaluation metrics payload.

    Handles the nested Shape A (metric key -> {"details": {...}}) used by the
    GPT-5.4-mini runs for both the falloesung and the custom GP judge, plus
    flat-key fallbacks.
    """
    if not isinstance(metrics, dict):
        return None, None
    for key, val in metrics.items():
        if not key.startswith("llm_judge"):
            continue
        if isinstance(val, dict):
            details = val.get("details") if isinstance(val.get("details"), dict) else val
            for raw_key in ("raw_score", "total_score", "score"):
                if details.get(raw_key) is not None:
                    raw = float(details[raw_key])
                    passed = details.get("passed")
                    return raw, (bool(passed) if passed is not None
                                 else raw >= PASS_RAW)
    for raw_key in ("llm_judge_falloesung_raw", "raw_score", "total_score"):
        if metrics.get(raw_key) is not None:
            raw = float(metrics[raw_key])
            passed = metrics.get("llm_judge_falloesung_passed")
            return raw, (bool(passed) if passed is not None else raw >= PASS_RAW)
    return None, None


def _md(gen):
    md = gen.get("response_metadata")
    if isinstance(md, str):
        try:
            md = json.loads(md)
        except json.JSONDecodeError:
            md = {}
    return md or {}


def _stats_from_rows(rows):
    """rows: list of dicts with raw, passed, latency_ms, cost, words, trunc."""
    if not rows:
        return None
    raws = [r["raw"] for r in rows if r["raw"] is not None]
    lat = [r["latency_ms"] for r in rows if r["latency_ms"] is not None]
    cost = [r["cost"] for r in rows if r["cost"] is not None]
    words = [r["words"] for r in rows if r["words"] is not None]
    return {
        "n": len(raws),
        "judge_raw_mean": statistics.mean(raws) if raws else None,
        "judge_raw_stdev": (statistics.stdev(raws) if len(raws) > 1 else None),
        "pass_rate": (sum(1 for r in rows if r["passed"]) / len(raws)
                      if raws else None),
        "truncated": sum(1 for r in rows if r["trunc"]),
        "mean_latency_s": statistics.mean(lat) / 1000 if lat else None,
        "mean_words": round(statistics.mean(words)) if words else None,
        "mean_cost_usd": statistics.mean(cost) if cost else None,
        "total_retries": sum(r.get("retries") or 0 for r in rows),
    }


def _rows_from_generations(gens, judge_prefix):
    rows = []
    for g in gens:
        raw = passed = None
        for ev in g.get("evaluations") or []:
            fn = ev.get("field_name") or ""
            if not fn.startswith(judge_prefix):
                continue
            raw, passed = _judge_raw_from_metrics(ev.get("metrics"))
            if raw is not None:
                break
        md = _md(g)
        content = g.get("response_content") or ""
        # cost_usd of 0.0 means the billing route did not price the call
        # (per-user provider keys) — treat as missing, not free.
        _cost = md.get("cost_usd")
        rows.append({
            "raw": raw, "passed": passed,
            "latency_ms": md.get("response_time_ms"),
            "cost": _cost if _cost else None,
            "words": len(content.split()) if isinstance(content, str) and content else None,
            "trunc": bool(md.get("truncated")),
            "retries": md.get("retry_count") or 0,
        })
    # Only judge-scored generations enter the paired table (matches how the
    # leaderboard counts n).
    return [r for r in rows if r["raw"] is not None]


def main():
    out = {"_meta": {
        "thinking_model": THINKING,
        "instruct_model": INSTRUCT,
        "pass_threshold_raw": PASS_RAW,
        "sources": {
            "thinking_benchathon": "data/raw/benchathon/Benchathon-tasks-2026-05-31.json",
            "thinking_grundprinzipien": "data/processed/grundprinzipien_model_summary.json + operational_metadata.json",
            "instruct": "data/raw/ablation/qwen_instruct_ablation.json",
        },
    }, "corpora": {}}

    # ---- Thinking, Benchathon: from the canonical export -------------------
    bench = _load(RAW / "benchathon" / "Benchathon-tasks-2026-05-31.json")
    thinking_gens = [g for t in bench["tasks"]
                     for g in (t.get("generations") or [])
                     if g.get("model_id") == THINKING]
    bench_thinking = _stats_from_rows(
        _rows_from_generations(thinking_gens, BENCH_PRIMARY_PREFIX))

    # ---- Thinking, Grundprinzipien: judge stats from the model summary -----
    gp_summary = _load(PROCESSED / "grundprinzipien_model_summary.json")
    gp_row = next((r for r in gp_summary
                   if THINKING in (r.get("system") or "")), None)
    op = _load(PROCESSED / "operational_metadata.json")
    gp_op = (op.get("per_corpus") or {}).get("grundprinzipien", {}).get(THINKING, {})
    gp_thinking = None
    if gp_row:
        m = gp_row.get("metrics") or {}
        gp_thinking = {
            "n": m.get("judge_raw_n") or gp_row.get("n_generations"),
            "judge_raw_mean": m.get("judge_raw_mean"),
            "judge_raw_stdev": m.get("judge_raw_stdev"),
            "pass_rate": m.get("judge_pass_rate"),
            "truncated": gp_op.get("truncated"),
            "mean_latency_s": gp_op.get("mean_latency_s"),
            "mean_words": gp_op.get("mean_words"),
            "mean_cost_usd": gp_op.get("mean_cost_usd"),
            "total_retries": gp_op.get("total_retries"),
        }

    # ---- Instruct, both corpora: from the ablation sidecar -----------------
    sidecar = _load(RAW / "ablation" / "qwen_instruct_ablation.json")
    inst = {}
    for corpus, blob in (sidecar.get("corpora") or {}).items():
        evals_by_gen = {}
        for ev in blob.get("evaluations") or []:
            evals_by_gen.setdefault(ev["generation_id"], []).append(ev)
        gens = []
        for g in blob.get("generations") or []:
            g = dict(g)
            g["evaluations"] = evals_by_gen.get(g["generation_id"], [])
            gens.append(g)
        prefix = "llm_judge"  # sidecar already filtered to the primary prefix
        inst[corpus] = _stats_from_rows(_rows_from_generations(gens, prefix))

    out["corpora"]["benchathon"] = {
        "thinking": bench_thinking, "instruct": inst.get("benchathon")}
    out["corpora"]["grundprinzipien"] = {
        "thinking": gp_thinking, "instruct": inst.get("grundprinzipien")}

    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    for corpus, pair in out["corpora"].items():
        for variant, s in pair.items():
            if s:
                print(f"{corpus}/{variant}: n={s['n']} raw={s['judge_raw_mean']:.1f} "
                      f"pass={s['pass_rate']:.0%} trunc={s['truncated']}")
            else:
                print(f"{corpus}/{variant}: MISSING")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
