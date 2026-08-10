#!/usr/bin/env python3
"""Pull tailored-arm judge rows out of the local DB into a tidy JSONL.

Reads ``judge_run_log.jsonl`` (one dispatched evaluation per exam) and
``picks.json`` (the 45 dataset-paper targets), then exports every
``task_evaluations`` row belonging to those runs whose generation_id /
annotation_id is one of the 45 picks — the 3 over-selected same-model
sibling generations are dropped here, at the analysis boundary.

Each output row: pick_id, task_id, target_type, target_id, judge model,
judge run index, per-step scores, total, and the rubric_id the judge used
(from details, for the D6 selection cross-check).

Usage: uv run python scripts/analysis/extract_judge_results.py
Output: data/interim/judge_results.jsonl (overwritten)
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
PICKS = HERE / "data" / "interim" / "picks.json"
RUN_LOG = HERE / "data" / "interim" / "judge_run_log.jsonl"
OUT = HERE / "data" / "interim" / "judge_results.jsonl"


def _psql_json(query: str):
    out = subprocess.run(
        ["docker", "exec", "benger-db-1", "psql", "-U", "postgres", "-d", "benger",
         "-tAc", f"select coalesce(json_agg(t), '[]') from ({query}) t;"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return json.loads(out)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--picks", default=str(PICKS))
    parser.add_argument("--log", default=str(RUN_LOG))
    parser.add_argument("--out", default=str(OUT))
    parser.add_argument("--metric", default="llm_judge_rubric",
                        choices=["llm_judge_rubric", "llm_judge_falloesung"],
                        help="Metric family to read from te.metrics "
                             "(llm_judge_falloesung for the matched holistic arms)")
    parser.add_argument("--config-prefix",
                        help="Comma-separated field_name config prefixes to KEEP. Needed when "
                             "a log's evaluation_ids also contain dead sibling-config rows "
                             "(e.g. the rep3 ids carry -repA/-o5 credit-failure rows).")
    parser.add_argument("--dedupe-latest", action="store_true",
                        help="When a cell was judged by more than one logged evaluation "
                             "(e.g. smoke + fleet re-dispatch under force_rerun), keep only "
                             "the newest row per (target, judge, run_index, config)")
    args = parser.parse_args()
    picks_path, out_path = Path(args.picks), Path(args.out)
    log_paths = [Path(p.strip()) for p in args.log.split(",") if p.strip()]
    keep_prefixes = tuple(p.strip() for p in args.config_prefix.split(",")) if args.config_prefix else None

    picks = json.loads(picks_path.read_text(encoding="utf-8"))["resolved"]
    by_target = {p["target_id"]: p for p in picks}

    eval_ids = []
    for lp in log_paths:
        for line in lp.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row.get("evaluation_id"):
                eval_ids.append(row["evaluation_id"])
    eval_ids = sorted(set(eval_ids))
    print(f"{len(eval_ids)} dispatched evaluations across {len(log_paths)} log(s), "
          f"{len(by_target)} pick targets"
          + (f"; keep prefixes {keep_prefixes}" if keep_prefixes else ""))

    id_list = "','".join(eval_ids)
    rows = _psql_json(
        "select te.id, te.evaluation_id, te.task_id, te.generation_id, "
        "te.annotation_id, te.field_name, te.metrics, te.created_at, "
        "ejr.judge_model_id, ejr.run_index "
        "from task_evaluations te "
        "left join evaluation_judge_runs ejr on te.judge_run_id = ejr.id "
        f"where te.evaluation_id in ('{id_list}')"
    )

    kept_rows, dropped = [], 0
    for r in rows:
        # Mirror the control arm's field scoping: generations judged as
        # __all_model__, annotations on human:loesung. Any other field row
        # (e.g. human:gliederung from the early smoke) is out of scope.
        fname = r.get("field_name") or ""
        if not ("|__all_model__|" in fname or "|human:loesung|" in fname):
            dropped += 1
            continue
        if keep_prefixes and not fname.split("|", 1)[0] in keep_prefixes:
            dropped += 1
            continue
        target_id = r.get("generation_id") or r.get("annotation_id")
        pick = by_target.get(target_id)
        if pick is None:
            dropped += 1
            continue
        metrics = r.get("metrics") or {}
        m = metrics.get(args.metric) or {}
        details = m.get("details") or {}
        out_row = {
            "pick_id": pick["pick_id"],
            "provenance": pick["provenance"],
            "task_id": r["task_id"],
            "target_type": pick["target_type"],
            "target_id": target_id,
            "judge_model_id": r.get("judge_model_id"),
            "judge_run_index": r.get("run_index"),
            "field_name": r.get("field_name"),
            "score": m.get("value"),
            "error": metrics.get("error") or m.get("error"),
            "created_at": r.get("created_at"),
        }
        if args.metric == "llm_judge_falloesung":
            # Falloesung details carry raw_score (0-100) + judge_response with
            # the 10 nested dimensions; there is no total_score/scores pair.
            raw = details.get("raw_score")
            if raw is None and m.get("value") is not None:
                raw = float(m["value"]) * 100.0
            cm = details.get("call_metadata") or {}
            out_row.update({
                "total_score": float(raw) if raw is not None else None,
                "total_max": 100.0,
                "scores": (details.get("judge_response") or {}).get("dimensions"),
                "rubric_id": None,
                "grade_points": details.get("grade_points"),
                "cm_temperature": cm.get("temperature"),
                "cm_max_tokens": cm.get("max_tokens"),
                "truncated": cm.get("truncated"),
            })
        else:
            out_row.update({
                "total_score": details.get("total_score"),
                "total_max": details.get("total_max"),
                "scores": details.get("scores"),
                "rubric_id": details.get("rubric_id"),
            })
        kept_rows.append(out_row)

    deduped = 0
    if args.dedupe_latest:
        latest = {}
        for row in kept_rows:
            key = (row["target_id"], row["judge_model_id"], row["judge_run_index"],
                   (row["field_name"] or "").split("|", 1)[0])
            prev = latest.get(key)
            if prev is None or (row["created_at"] or "") > (prev["created_at"] or ""):
                latest[key] = row
        deduped = len(kept_rows) - len(latest)
        kept_rows = sorted(latest.values(), key=lambda x: (x["pick_id"], x["judge_model_id"] or "",
                                                           x["judge_run_index"] or 0))
    with out_path.open("w", encoding="utf-8") as fh:
        for row in kept_rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"kept {len(kept_rows)} rows -> {out_path}; dropped {dropped} non-pick rows"
          + (f"; deduped {deduped} superseded rows" if args.dedupe_latest else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
