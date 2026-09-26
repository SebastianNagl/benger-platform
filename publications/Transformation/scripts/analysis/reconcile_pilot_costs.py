#!/usr/bin/env python3
"""Reconcile the pilot rows' costs with the spend ledger.

The rows of scripts/ops/pilot.sh carry the cost of every provider call; the
ledger (data/interim/pilot/ledger.json) books every call as it happens. The
two must agree once the rows are read without double counting:

  - the D1 pilot files overlap (probes.jsonl holds every row of
    probes_gate.jsonl and probes_luna_fixed.jsonl), so a plain sum over the
    files counts those calls twice; calls are counted once per fingerprint
    (model, tokens, cost, latency, prompt hash; pilot_rows.call_fingerprint);
  - spend before the wrapper existed (P1) has no run id in the ledger; its
    total is the ledger's spent_before at the first recorded run, and its
    per-model split is the container ledger of that time
    (ledger_p1_container.json, when present);
  - runs with a run id are compared run by run (rows of that run id against
    the run's "added").

Output: <data root>/interim/pilot/cost_reconciliation.json (git-ignored) and
a console summary. The data root comes from scripts/local_config.py.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
sys.path[:0] = [str(HERE / "scripts"), str(HERE / "scripts" / "analysis")]

import local_config
from pilot_rows import call_fingerprint, is_dry, load_rows

TOL = 1e-4


def by_model(calls) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = defaultdict(lambda: {"calls": 0, "usd": 0.0})
    for call in calls:
        m = out[call.get("model") or "?"]
        m["calls"] += 1
        m["usd"] = round(m["usd"] + float(call.get("usd") or 0.0), 6)
    return dict(out)


def main() -> int:
    data = local_config.data_root()
    pilot, human = data / "interim" / "pilot", data / "interim" / "human" / "pilot"
    ledger = json.loads((pilot / "ledger.json").read_text())
    files = sorted(p for p in pilot.glob("*.jsonl") if not p.name.endswith("-coverage.jsonl"))
    d2_files = sorted(p for p in human.glob("*.jsonl") if not p.name.endswith("-coverage.jsonl")) if human.exists() else []

    per_file, all_calls = {}, []
    for path in files + d2_files:
        rows = load_rows([path])
        live = [r for r in rows if not is_dry(r)]
        calls = [(r, c) for r in live for c in r.get("calls") or [] if not c.get("dry_run")]
        per_file[str(path.relative_to(data))] = {"rows": len(rows), "live_rows": len(live), "calls": len(calls),
                                                 "usd": round(sum(float(c.get("usd") or 0) for _, c in calls), 4)}
        all_calls += calls
    distinct: dict[tuple, tuple] = {}
    for row, call in all_calls:
        distinct.setdefault(call_fingerprint(call), (row, call))

    runs = ledger.get("runs") or []
    legacy_spent = float(runs[0]["spent_before"]) if runs else float(ledger["spent"])
    legacy_calls = [c for r, c in distinct.values() if not r.get("run_id")]
    run_calls: dict[str, list] = defaultdict(list)
    for r, c in distinct.values():
        if r.get("run_id"):
            run_calls[r["run_id"]].append(c)
    per_run = []
    for run in runs:
        rows_usd = round(sum(float(c.get("usd") or 0) for c in run_calls.get(run["run_id"], [])), 5)
        per_run.append({"run_id": run["run_id"], "phase": run["phase"], "dry_run": run.get("dry_run"),
                        "ledger_added": round(float(run.get("added") or 0), 5), "rows_usd": rows_usd,
                        "match": abs(rows_usd - float(run.get("added") or 0)) < TOL})
    p1_container = pilot / "ledger_p1_container.json"
    p1_models = json.loads(p1_container.read_text()).get("by_model") if p1_container.exists() else None
    legacy_models = by_model(legacy_calls)
    legacy_usd = round(sum(float(c.get("usd") or 0) for c in legacy_calls), 4)
    d1_raw = round(sum(v["usd"] for k, v in per_file.items() if k.startswith("interim/pilot/")), 4)
    report = {
        "files": per_file,
        "d1_rows_plain_sum_usd": d1_raw,
        "distinct_calls": len(distinct), "calls_in_files": len(all_calls),
        "legacy": {"ledger_spent_before_first_run": round(legacy_spent, 4), "rows_distinct_usd": legacy_usd,
                   "gap_usd": round(legacy_spent - legacy_usd, 4), "rows_by_model": legacy_models,
                   "ledger_by_model": p1_models,
                   "gap_by_model": {m: {"calls": v["calls"] - legacy_models.get(m, {}).get("calls", 0),
                                        "usd": round(v["usd"] - legacy_models.get(m, {}).get("usd", 0.0), 4)}
                                    for m, v in (p1_models or {}).items()}},
        "runs": per_run,
        "runs_matching": sum(1 for r in per_run if r["match"]), "runs_total": len(per_run),
        "ledger_spent": round(float(ledger["spent"]), 4),
        "rows_distinct_usd_total": round(sum(float(c.get("usd") or 0) for _, c in distinct.values()), 4),
    }
    out = pilot / "cost_reconciliation.json"
    out.write_text(json.dumps(report, indent=1) + "\n")

    print(f"D1 files, plain sum over rows: ${d1_raw:.2f} ({len(all_calls)} calls in all files, "
          f"{len(distinct)} distinct)")
    print(f"P1 (before the first recorded run): ledger ${legacy_spent:.4f}, distinct rows ${legacy_usd:.4f}, "
          f"gap ${legacy_spent - legacy_usd:.4f}")
    for model, gap in report["legacy"]["gap_by_model"].items():
        if gap["calls"] or abs(gap["usd"]) > TOL:
            print(f"  {model}: {gap['calls']} ledger calls without a row, ${gap['usd']:.4f}")
    print(f"recorded runs: {report['runs_matching']}/{report['runs_total']} match the ledger run by run")
    for r in per_run:
        if not r["match"]:
            print(f"  MISMATCH {r['run_id']} {r['phase']}: ledger +${r['ledger_added']:.4f}, rows ${r['rows_usd']:.4f}")
    print(f"ledger total ${report['ledger_spent']:.4f}; distinct rows total ${report['rows_distinct_usd_total']:.4f}")
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
