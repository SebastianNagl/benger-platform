"""Derive error-analysis failure modes across all three corpora from the current
GPT-5.4-mini judges, with per-system-tier breakdowns, mode overlap, and a
representative worked example per mode.

Sources (per-generation, current primary judge only):
  - Benchathon : data/processed/benchathon_model_evaluations.json (judge mptmfvee)
                 + text/word counts from data/raw/benchathon/Benchathon_export.json
  - ZJS        : data/raw/zjs/zjs_faelle_full_export.json  (judge mptrd45m, streamed)
  - Grundprinz.: data/raw/grundprinzipien/..._full_export.json (judge mpu1cuad)

Benchathon and ZJS share the 10-dim Falllösung rubric and use the same modes;
Grundprinzipien uses the custom 4-dim rubric + a binary Ja/Nein decision (matched
to gold via scripts/_gp_decision.py, NOT the buggy exact-match metric) and gets
decision-centred modes. System tier (flagship / efficiency / open_reference)
comes from data/processed/systems.json. Every count is reproducible.

Outputs:
  data/processed/error_analysis.json              -- per-corpus counts, per-tier
                                                     rates, coupling, mode overlap,
                                                     one worked example per mode
  data/processed/error_review_falloesung.csv      -- one row per flagged Falllösung case
  data/processed/error_review_grundprinzipien.csv -- one row per flagged GP case

    uv run python scripts/derive_error_analysis.py
"""

from __future__ import annotations

import csv
import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

import ijson

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _gp_decision import decision_accuracy  # noqa: E402

HERE = Path(__file__).resolve().parent.parent
PROCESSED = HERE / "data" / "processed"
RAW = HERE / "data" / "raw"
OUT = PROCESSED / "error_analysis.json"
OUT_REVIEW_FALL = PROCESSED / "error_review_falloesung.csv"
OUT_REVIEW_GP = PROCESSED / "error_review_grundprinzipien.csv"

BENCH_EVALS = PROCESSED / "benchathon_model_evaluations.json"
BENCH_RAW = RAW / "benchathon" / "Benchathon_export.json"
ZJS_RAW = RAW / "zjs" / "zjs_faelle_full_export.json"
ZJS_PREFIX = "llm_judge_falloesung-mptrd45m"
GP_RAW = RAW / "grundprinzipien" / "grundprinzipien_Grundprinzipien_full_export.json"
GP_PREFIX = "llm_judge_custom-mpu1cuad"
SYSTEMS = PROCESSED / "systems.json"

FALL_MAX = {
    "sprache": 3, "formalia": 2, "gliederung": 5, "subsumtion": 15,
    "rechtskenntnis": 15, "rechtsgrundlagen": 10, "vollstaendigkeit": 10,
    "methodischer_stil": 10, "schwerpunktsetzung": 10, "ergebnisrichtigkeit": 20,
}
GP_MAX = {"result_correctness": 40, "legal_knowledge": 25,
          "subsumption": 25, "clarity": 10}

SHORT_MAX_WORDS = 200
LONG_MIN_WORDS = 2000
LOW, MID, HIGH = 0.40, 0.50, 0.60
REVIEW_MIN_RATE = 0.01
TIER_ORDER = ["flagship", "efficiency", "open_reference"]
FALL_EXCERPT, GP_EXCERPT = 1000, 4000


def fl(x):
    return None if x is None else float(x)


def _text(rc):
    if isinstance(rc, str):
        return rc
    if isinstance(rc, dict):
        return max((v for v in rc.values() if isinstance(v, str)), key=len, default="")
    return ""


def _excerpt(rc, n):
    return " ".join(_text(rc)[:n].split())


def frac(dims, key, dim_max):
    v = (dims or {}).get(key)
    return None if v is None else v / dim_max[key]


def _ff(dims, key, dim_max, default):
    v = frac(dims, key, dim_max)
    return default if v is None else v


def load_tiers():
    out = {}
    if SYSTEMS.exists():
        for s in json.load(open(SYSTEMS, encoding="utf-8")):
            mid, t = s.get("model_id"), s.get("tier")
            if mid:
                out[mid] = t
                out[mid.split("/")[-1]] = t
    return out


def tier_of(system, tiers):
    return tiers.get(system) or tiers.get(str(system).split("/")[-1]) or "other"


# ---- mode definitions -------------------------------------------------------
def _fall_mode_defs():
    def d(g):
        return g["dimensions"]
    return [
        ("long_but_shallow", "Long-but-shallow",
         f"word_count >= {LONG_MIN_WORDS} AND subsumtion <= {MID}*max AND schwerpunktsetzung <= {MID}*max",
         lambda g: (g["word_count"] is not None and g["word_count"] >= LONG_MIN_WORDS
                    and _ff(d(g), "subsumtion", FALL_MAX, 1) <= MID
                    and _ff(d(g), "schwerpunktsetzung", FALL_MAX, 1) <= MID),
         lambda g: -(g["word_count"] or 0)),
        ("short_missing_subsumption", "Missing/perfunctory subsumption in short answers",
         f"word_count < {SHORT_MAX_WORDS} AND subsumtion <= {LOW}*max",
         lambda g: (g["word_count"] is not None and g["word_count"] < SHORT_MAX_WORDS
                    and _ff(d(g), "subsumtion", FALL_MAX, 1) <= LOW),
         lambda g: (g["word_count"] or 0)),
        ("wrong_norm_framing", "Wrong-norm framing",
         f"rechtsgrundlagen <= {LOW}*max AND rechtskenntnis <= {LOW}*max AND methodischer_stil >= {MID}*max",
         lambda g: (_ff(d(g), "rechtsgrundlagen", FALL_MAX, 1) <= LOW
                    and _ff(d(g), "rechtskenntnis", FALL_MAX, 1) <= LOW
                    and _ff(d(g), "methodischer_stil", FALL_MAX, 0) >= MID),
         lambda g: _ff(d(g), "rechtsgrundlagen", FALL_MAX, 1) + _ff(d(g), "rechtskenntnis", FALL_MAX, 1)),
        ("correct_outcome_weak_subsumption", "Correct outcome, weak subsumption",
         f"ergebnisrichtigkeit >= {HIGH}*max AND subsumtion <= {LOW}*max",
         lambda g: (_ff(d(g), "ergebnisrichtigkeit", FALL_MAX, 0) >= HIGH
                    and _ff(d(g), "subsumtion", FALL_MAX, 1) <= LOW),
         lambda g: -_ff(d(g), "ergebnisrichtigkeit", FALL_MAX, 0)),
        ("wrong_outcome_good_subsumption", "Wrong outcome despite plausible reasoning",
         f"subsumtion >= {HIGH}*max AND ergebnisrichtigkeit <= {LOW}*max",
         lambda g: (_ff(d(g), "subsumtion", FALL_MAX, 0) >= HIGH
                    and _ff(d(g), "ergebnisrichtigkeit", FALL_MAX, 1) <= LOW),
         lambda g: -_ff(d(g), "subsumtion", FALL_MAX, 0)),
    ]


def _gp_mode_defs():
    def d(g):
        return g["dimensions"]
    return [
        ("wrong_decision", "Wrong Ja/Nein decision", "accuracy == 0",
         lambda g: g.get("accuracy") == 0,
         lambda g: _ff(d(g), "subsumption", GP_MAX, 1)),
        ("correct_decision_weak_subsumption", "Correct decision, weak subsumption",
         f"accuracy == 1 AND subsumption <= {LOW}*max",
         lambda g: g.get("accuracy") == 1 and _ff(d(g), "subsumption", GP_MAX, 1) <= LOW,
         lambda g: _ff(d(g), "subsumption", GP_MAX, 1)),
        ("wrong_decision_sound_subsumption", "Wrong decision despite sound subsumption",
         f"accuracy == 0 AND subsumption >= {HIGH}*max AND result_correctness <= {LOW}*max",
         lambda g: (g.get("accuracy") == 0 and _ff(d(g), "subsumption", GP_MAX, 0) >= HIGH
                    and _ff(d(g), "result_correctness", GP_MAX, 1) <= LOW),
         lambda g: -_ff(d(g), "subsumption", GP_MAX, 0)),
    ]


def _example(g):
    return {"system": g["system"], "tier": g.get("tier"), "task_id": g["task_id"],
            "generation_id": g["generation_id"], "word_count": g.get("word_count"),
            "accuracy": g.get("accuracy"), "raw_score": g.get("raw_score"),
            "dimensions": g["dimensions"], "excerpt": (g.get("excerpt") or "")[:600]}


def _by_tier(hits, tier_n):
    bt = Counter(g["tier"] for g in hits)
    return {t: {"count": bt.get(t, 0), "n": n, "rate": (bt.get(t, 0) / n) if n else None}
            for t, n in tier_n.items()}


def _summarise(gens, defs):
    """Common mode summary: count, rate, per-tier rate, worked example. Returns
    (summary_dict, hits_by_mode)."""
    n = len(gens)
    tier_n = Counter(g["tier"] for g in gens)
    summary, hits = {}, {}
    for key, label, crit, pred, rank in defs:
        h = sorted([g for g in gens if pred(g)], key=rank)
        hits[key] = h
        summary[key] = {
            "label": label, "criteria": crit, "count": len(h),
            "rate": (len(h) / n) if n else None,
            "by_tier": _by_tier(h, tier_n),
            "example": _example(h[0]) if h else None,
            "generation_ids": [g["generation_id"] for g in h[:500]],
        }
    return summary, hits, dict(tier_n)


def fall_modes(gens, judge):
    summary, hits, tier_n = _summarise(gens, _fall_mode_defs())
    ls = {g["generation_id"] for g in hits["long_but_shallow"]}
    wn = {g["generation_id"] for g in hits["wrong_norm_framing"]}
    pairs = [(frac(g["dimensions"], "subsumtion", FALL_MAX),
              frac(g["dimensions"], "ergebnisrichtigkeit", FALL_MAX)) for g in gens]
    pairs = [(a, b) for a, b in pairs if a is not None and b is not None]
    coupling = statistics.correlation([a for a, _ in pairs], [b for _, b in pairs]) if len(pairs) > 1 else None
    return ({"judge": judge, "rubric": "falloesung_10dim", "n": len(gens),
             "tier_n": tier_n,
             "coupling_subsumtion_ergebnis_pearson": coupling,
             "overlap_longshallow_wrongnorm": len(ls & wn),
             "modes": summary}, hits)


def gp_modes(gens, judge):
    scored = [g for g in gens if g.get("accuracy") is not None]
    summary, hits, tier_n = _summarise(scored, _gp_mode_defs())
    pairs = [(frac(g["dimensions"], "subsumption", GP_MAX),
              frac(g["dimensions"], "result_correctness", GP_MAX)) for g in gens]
    pairs = [(a, b) for a, b in pairs if a is not None and b is not None]
    coupling = statistics.correlation([a for a, _ in pairs], [b for _, b in pairs]) if len(pairs) > 1 else None
    acc = [g["accuracy"] for g in scored]
    # per-tier Ja/Nein accuracy as well (the headline GP metric)
    acc_by_tier = {}
    for t in set(g["tier"] for g in scored):
        vals = [g["accuracy"] for g in scored if g["tier"] == t]
        acc_by_tier[t] = {"n": len(vals), "accuracy": statistics.mean(vals) if vals else None}
    return ({"judge": judge, "rubric": "custom_4dim", "n": len(gens),
             "n_with_decision": len(scored), "tier_n": tier_n,
             "accuracy": statistics.mean(acc) if acc else None,
             "accuracy_by_tier": acc_by_tier,
             "coupling_subsumption_result_pearson": coupling,
             "modes": summary}, hits)


# ---- extractors -------------------------------------------------------------
def load_benchathon(tiers):
    evals = json.load(open(BENCH_EVALS, encoding="utf-8"))
    raw = json.load(open(BENCH_RAW, encoding="utf-8"))
    text = {g.get("id"): g.get("response_content")
            for t in raw.get("tasks", []) for g in (t.get("generations") or [])}
    gens = []
    for r in evals:
        rc = text.get(r["generation_id"])
        gens.append({"system": r["system"], "tier": tier_of(r["system"], tiers),
                     "task_id": r["task_id"], "generation_id": r["generation_id"],
                     "word_count": len(_text(rc).split()), "raw_score": r.get("raw_score"),
                     "excerpt": _excerpt(rc, FALL_EXCERPT),
                     "dimensions": r.get("dimensions") or {}})
    return gens


def _fall_eval(metrics):
    kf = (metrics or {}).get("llm_judge_falloesung")
    if not isinstance(kf, dict):
        return None, None
    det = kf.get("details") or {}
    if det.get("raw_score") is None:
        return None, None
    dims_src = (det.get("judge_response") or {}).get("dimensions") or det.get("dimensions") or {}
    dims = {k: fl(v.get("score")) for k, v in dims_src.items()
            if isinstance(v, dict) and v.get("score") is not None}
    return dims, fl(det.get("raw_score"))


def stream_zjs(tiers):
    if not ZJS_RAW.exists():
        print("  ZJS source missing; skipping", file=sys.stderr)
        return None
    gens, t0, n = [], time.time(), 0
    with ZJS_RAW.open("rb") as f:
        for task in ijson.items(f, "tasks.item"):
            tid = task.get("id"); n += 1
            for g in (task.get("generations") or []):
                mid = g.get("model_id")
                if not mid:
                    continue
                dims = raw_score = None
                for ev in (g.get("evaluations") or []):
                    if str(ev.get("field_name") or "").startswith(ZJS_PREFIX):
                        dims, raw_score = _fall_eval(ev.get("metrics"))
                        if dims:
                            break
                if not dims:
                    continue
                rc = g.get("response_content")
                gens.append({"system": mid, "tier": tier_of(mid, tiers), "task_id": tid,
                             "generation_id": g.get("id"),
                             "word_count": len(_text(rc).split()), "raw_score": raw_score,
                             "excerpt": _excerpt(rc, FALL_EXCERPT), "dimensions": dims})
            if n % 100 == 0:
                print(f"  ... ZJS {n} tasks, {len(gens)} gens, {time.time()-t0:.0f}s", file=sys.stderr)
    print(f"  ZJS: {len(gens)} primary-judged gens in {time.time()-t0:.0f}s", file=sys.stderr)
    return gens


def load_gp(tiers):
    if not GP_RAW.exists():
        print("  GP source missing; skipping", file=sys.stderr)
        return None
    export = json.load(open(GP_RAW, encoding="utf-8"))
    gens = []
    for t in export.get("tasks", []):
        tid = t.get("id")
        gold = (t.get("data") or {}).get("binary_solution")
        for g in (t.get("generations") or []):
            mid = g.get("model_id")
            if not mid:
                continue
            dims = judge_raw = None
            for ev in (g.get("evaluations") or []):
                fn = str(ev.get("field_name") or ""); m = ev.get("metrics") or {}
                if fn.startswith(GP_PREFIX) and isinstance(m.get("llm_judge_custom"), dict):
                    det = m["llm_judge_custom"].get("details") or {}
                    sc = det.get("scores") or {}
                    dims = {k: fl(v.get("score")) for k, v in sc.items()
                            if isinstance(v, dict) and v.get("score") is not None}
                    judge_raw = fl(det.get("total_score"))
            if dims:
                acc = decision_accuracy(g.get("response_content"), gold)  # normalised match
                gens.append({"system": mid, "tier": tier_of(mid, tiers), "task_id": tid,
                             "generation_id": g.get("id"),
                             "accuracy": int(acc) if acc is not None else None,
                             "raw_score": judge_raw,
                             "excerpt": _excerpt(g.get("response_content"), GP_EXCERPT),
                             "dimensions": dims})
    return gens


# ---- review-CSV writers -----------------------------------------------------
def write_review(path, corpus_hits, summary_by_corpus, kind):
    if kind == "fall":
        dims = ["subsumtion", "schwerpunktsetzung", "rechtsgrundlagen",
                "rechtskenntnis", "methodischer_stil", "ergebnisrichtigkeit"]
        cols = ["corpus", "mode", "system", "tier", "task_id", "generation_id",
                "word_count", "raw_score"] + dims + ["excerpt"]
    else:
        dims = ["result_correctness", "legal_knowledge", "subsumption", "clarity"]
        cols = ["corpus", "mode", "system", "tier", "task_id", "generation_id",
                "accuracy", "raw_score"] + dims + ["excerpt"]
    n_written = 0
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for corpus, hits_by_mode in corpus_hits.items():
            n = summary_by_corpus[corpus]["n"]
            for mode, hits in hits_by_mode.items():
                if n and len(hits) / n <= REVIEW_MIN_RATE:
                    continue
                for g in hits:
                    base = [corpus, mode, g["system"], g.get("tier"), g["task_id"], g["generation_id"]]
                    base += ([g.get("word_count"), g.get("raw_score")] if kind == "fall"
                             else [g.get("accuracy"), g.get("raw_score")])
                    base += [g["dimensions"].get(dn) for dn in dims]
                    base += [g.get("excerpt", "")]
                    w.writerow(base)
                    n_written += 1
    return n_written


def main():
    tiers = load_tiers()
    result, fall_hits, gp_hits = {}, {}, {}

    print("Benchathon ...", file=sys.stderr)
    result["benchathon"], fall_hits["benchathon"] = fall_modes(load_benchathon(tiers), "gpt-5.4-mini")

    print("ZJS (streaming) ...", file=sys.stderr)
    zjs = stream_zjs(tiers)
    if zjs is not None:
        result["zjs"], fall_hits["zjs"] = fall_modes(zjs, "gpt-5.4-mini")

    print("Grundprinzipien ...", file=sys.stderr)
    gp = load_gp(tiers)
    if gp is not None:
        result["grundprinzipien"], gp_hits["grundprinzipien"] = gp_modes(gp, "gpt-5.4-mini")

    with OUT.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    n_fall = write_review(OUT_REVIEW_FALL, fall_hits, result, "fall")
    n_gp = write_review(OUT_REVIEW_GP, gp_hits, result, "gp") if gp_hits else 0

    for corpus, r in result.items():
        head = f"{corpus}: n={r['n']}"
        if "accuracy" in r:
            head += f", accuracy={r['accuracy']:.3f}, sub~result r={r['coupling_subsumption_result_pearson']:.3f}"
        else:
            head += (f", sub~ergebnis r={r['coupling_subsumtion_ergebnis_pearson']:.3f}"
                     f", overlap={r['overlap_longshallow_wrongnorm']}")
        print(f"\n{head}  tiers={r['tier_n']}")
        for k, m in r["modes"].items():
            rate = m["rate"] or 0
            bt = " ".join(f"{t[:4]}={100*(m['by_tier'].get(t, {}).get('rate') or 0):.1f}%" for t in TIER_ORDER)
            keep = "rev" if rate > REVIEW_MIN_RATE else "om "
            print(f"  [{keep}] {m['count']:>5} ({rate*100:4.1f}%) {m['label'][:34]:34s} | {bt}")
    print(f"\nwrote {OUT.name}; review {OUT_REVIEW_FALL.name} ({n_fall}), {OUT_REVIEW_GP.name} ({n_gp})")


if __name__ == "__main__":
    main()
