#!/usr/bin/env python3
"""RQ1 descriptives over generated Bewertungsbögen (contract v2).

Inputs
  - ``data/raw/local/task_rubrics.json`` (from ``make pull``) — successful
    rubrics incl. ``generation_metadata.full_document``
  - ``data/interim/rubric_sweep_log.jsonl`` (from the sweep driver) — one
    row per (generator, task, dispatch series) INCLUDING failed series;
    failures never create task_rubrics rows, so the compliance table is
    impossible without this log.

Outputs
  - ``data/processed/rubric_run_summary.json`` — per-generator sweep health:
    series/success/failure/timeout counts, failure stages + contract
    categories, attempts, latency. THE per-model failure-rate table the
    paper reports (strict contract, no repair).
  - ``data/processed/rubric_stats.json`` — per-generator document
    observables (step counts, weight distribution, Gewichtungsklassen,
    Herkunft/provenance shares, Teilpunktstufen, alternative Lösungswege,
    Warnungen, Schwerpunkte) and, once ≥2 generators exist, cross-generator
    convergence per task.

Runs with whatever is present: missing inputs are soft-skipped so ``make
derive`` works on a bare checkout.
"""

from __future__ import annotations

import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
SRC = HERE / "data" / "raw" / "local" / "task_rubrics.json"
SWEEP_LOG = HERE / "data" / "interim" / "rubric_sweep_log.jsonl"
OUT_STATS = HERE / "data" / "processed" / "rubric_stats.json"
OUT_SUMMARY = HERE / "data" / "processed" / "rubric_run_summary.json"


def weight_entropy(weights) -> float:
    total = sum(weights)
    probs = [w / total for w in weights if w > 0]
    return -sum(p * math.log2(p) for p in probs)


def describe(values) -> dict:
    values = [v for v in values if v is not None]
    if not values:
        return {"n": 0}
    return {
        "n": len(values),
        "mean": round(statistics.mean(values), 2),
        "stdev": round(statistics.stdev(values), 2) if len(values) > 1 else 0.0,
        "min": min(values),
        "max": max(values),
    }


def _doc_observables(doc: dict) -> dict:
    """Flat observables of one v2 full_document."""
    steps = [
        s
        for section in doc.get("abschnitte") or []
        for s in section.get("schritte") or []
    ]
    stufen_counts = [
        len((s.get("bewertungshinweise") or {}).get("teilpunktstufen") or [])
        for s in steps
    ]
    alts = doc.get("alternative_loesungswege") or []
    warnungen = (doc.get("meta") or {}).get("warnungen") or []
    return {
        # v3 capability observable: the model aims its relative weights at
        # a 100-point Richtwert; the distance of the stated sum from 100
        # measures residual arithmetic (in)ability without any contract
        # pressure (apportionment normalizes regardless).
        "weight_sum": sum(
            s.get("gewicht") or 0 for s in steps if isinstance(s.get("gewicht"), int)
        ),
        "n_sections": len(doc.get("abschnitte") or []),
        "n_steps": len(steps),
        "n_schwerpunkte": len(doc.get("klausurschwerpunkte") or []),
        "klassen": Counter(s.get("gewichtungsklasse") for s in steps),
        "herkunft": Counter(s.get("herkunft") for s in steps),
        "abhaengig_steps": sum(1 for s in steps if s.get("abhaengig_von")),
        "folgefehler_steps": sum(1 for s in steps if s.get("folgefehlerhinweis")),
        "stufen_per_step": stufen_counts,
        "n_alternativen": len(alts),
        "alt_typen": Counter(a.get("typ") for a in alts),
        "alt_extern": sum(
            1 for a in alts if a.get("herkunft") == "extern_ergaenzt"
        ),
        "n_warnungen": len(warnungen),
        "warnung_typen": Counter(w.get("typ") for w in warnungen),
    }


def _load_sweep_log() -> list[dict]:
    if not SWEEP_LOG.exists():
        return []
    rows = []
    for line in SWEEP_LOG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def main() -> int:
    if not SRC.exists():
        # Soft skip: `make derive` must work on a checkout without the local
        # dev stack; stats simply stay at their last pulled state.
        print(f"missing {SRC.relative_to(HERE)} — run `make pull` first (skipped)")
        return 0
    rubrics = json.loads(SRC.read_text(encoding="utf-8"))
    # Archived rubrics (v1 pilot, superseded candidates) are history, not
    # sweep output.
    rubrics = [r for r in rubrics if r.get("status") != "archived"]

    by_generator = defaultdict(list)
    for r in rubrics:
        by_generator[r.get("generator_model_id") or "unknown"].append(r)

    # ------------------------------------------------------------------
    # Compliance / failure table (successes from DB + failures from log)
    # ------------------------------------------------------------------
    sweep_rows = _load_sweep_log()
    summary = {
        "n_rubrics": len(rubrics),
        "sweep_log_present": bool(sweep_rows),
        "generators": {},
    }
    log_by_gen = defaultdict(list)
    for row in sweep_rows:
        log_by_gen[row.get("generator_model_id") or "unknown"].append(row)

    for gen in sorted(set(by_generator) | set(log_by_gen)):
        rows = by_generator.get(gen, [])
        log_rows = log_by_gen.get(gen, [])
        totals = [
            sum(
                s.get("max_score", 0)
                for s in (r.get("criteria") or {}).values()
            )
            for r in rows
        ]
        attempts = [
            (r.get("generation_metadata") or {}).get("attempts") for r in rows
        ]
        attempts = [a for a in attempts if a]
        latencies = [
            (r.get("generation_metadata") or {}).get("latency_ms") for r in rows
        ]
        failed = [r for r in log_rows if r.get("outcome") == "failed"]
        timeouts = [r for r in log_rows if r.get("outcome") == "timeout"]
        n_series = len(log_rows) if log_rows else len(rows)
        stage_hist = Counter(f.get("error_stage") or "unknown" for f in failed)
        cat_hist = Counter(
            c for f in failed for c in (f.get("error_categories") or [])
        )
        # Attempt-level compliance: every failed series burned the full
        # 3-attempt budget; successes record their actual attempt count.
        summary["generators"][gen] = {
            "series": n_series,
            "rubrics": len(rows),
            "failed_series": len(failed),
            "timeout_series": len(timeouts),
            "series_failure_rate": (
                round((len(failed) + len(timeouts)) / n_series, 3)
                if n_series
                else None
            ),
            "sum_100_compliance": (
                sum(1 for t in totals if t == 100) / len(totals) if totals else None
            ),
            "first_attempt_rate": (
                sum(1 for a in attempts if a == 1) / len(attempts)
                if attempts
                else None
            ),
            "attempts_per_success": describe(attempts),
            "failure_stages": dict(stage_hist),
            "failure_contract_categories": dict(cat_hist),
            "latency_ms": describe(latencies),
        }

    # ------------------------------------------------------------------
    # Document observables per generator
    # ------------------------------------------------------------------
    stats = {"per_generator": {}, "cross_generator_convergence": None}
    for gen, rows in sorted(by_generator.items()):
        step_counts, entropies, max_weights, stufen_means = [], [], [], []
        klassen, herkunft, alt_typen, warnung_typen = (
            Counter(),
            Counter(),
            Counter(),
            Counter(),
        )
        weight_sums = []
        n_sections, n_sps, n_alts, n_warn = [], [], [], []
        abhaengig_total = folgefehler_total = extern_alts = 0
        total_steps = 0
        docs_seen = 0
        for r in rows:
            criteria = r.get("criteria") or {}
            weights = [s.get("max_score", 0) for s in criteria.values()]
            step_counts.append(len(criteria))
            if weights:
                entropies.append(round(weight_entropy(weights), 3))
                max_weights.append(max(weights))
            total_steps += len(criteria)

            doc = (r.get("generation_metadata") or {}).get("full_document")
            if isinstance(doc, dict):
                docs_seen += 1
                obs = _doc_observables(doc)
                klassen.update(obs["klassen"])
                herkunft.update(obs["herkunft"])
                alt_typen.update(obs["alt_typen"])
                warnung_typen.update(obs["warnung_typen"])
                weight_sums.append(obs["weight_sum"])
                n_sections.append(obs["n_sections"])
                n_sps.append(obs["n_schwerpunkte"])
                n_alts.append(obs["n_alternativen"])
                n_warn.append(obs["n_warnungen"])
                abhaengig_total += obs["abhaengig_steps"]
                folgefehler_total += obs["folgefehler_steps"]
                extern_alts += obs["alt_extern"]
                if obs["stufen_per_step"]:
                    stufen_means.append(
                        round(statistics.mean(obs["stufen_per_step"]), 2)
                    )

        herkunft_total = sum(herkunft.values())
        stats["per_generator"][gen] = {
            "rubrics": len(rows),
            "v2_documents": docs_seen,
            "step_count": describe(step_counts),
            "stated_weight_sum": describe(weight_sums),
            "weight_sum_abs_distance_from_100": describe(
                [abs(w - 100) for w in weight_sums]
            ),
            "share_exact_100": (
                round(sum(1 for w in weight_sums if w == 100) / len(weight_sums), 3)
                if weight_sums
                else None
            ),
            "weight_entropy_bits": describe(entropies),
            "heaviest_step_points": describe(max_weights),
            "sections": describe(n_sections),
            "schwerpunkte": describe(n_sps),
            "gewichtungsklassen": dict(klassen),
            "herkunft_counts": dict(herkunft),
            "herkunft_shares": (
                {k: round(v / herkunft_total, 3) for k, v in herkunft.items()}
                if herkunft_total
                else {}
            ),
            "teilpunktstufen_per_step": describe(stufen_means),
            "steps_with_dependencies": abhaengig_total,
            "steps_with_folgefehlerhinweis": folgefehler_total,
            "alternativen": describe(n_alts),
            "alternativen_typen": dict(alt_typen),
            "alternativen_extern": extern_alts,
            "warnungen": describe(n_warn),
            "warnung_typen": dict(warnung_typen),
        }

    # Cross-generator convergence: only meaningful with >=2 generators.
    if len(by_generator) >= 2:
        by_task = defaultdict(dict)
        for r in rubrics:
            by_task[r["task_id"]][r.get("generator_model_id")] = r
        per_task = []
        for task_id, gens in by_task.items():
            if len(gens) < 2:
                continue
            counts = [len((r.get("criteria") or {})) for r in gens.values()]
            per_task.append(
                {
                    "task_id": task_id,
                    "n_generators": len(gens),
                    "step_count_spread": max(counts) - min(counts),
                }
            )
        stats["cross_generator_convergence"] = {
            "n_tasks_with_multiple_generators": len(per_task),
            "step_count_spread": describe(
                [t["step_count_spread"] for t in per_task]
            ),
            "per_task": per_task,
        }
    else:
        stats["cross_generator_convergence"] = None
        stats["note"] = (
            "single-generator data; convergence metrics require the "
            "multi-generator sweep"
        )

    OUT_STATS.parent.mkdir(parents=True, exist_ok=True)
    OUT_STATS.write_text(json.dumps(stats, ensure_ascii=False, indent=2), "utf-8")
    OUT_SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), "utf-8")
    print(f"wrote {OUT_STATS.relative_to(HERE)} and {OUT_SUMMARY.relative_to(HERE)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
