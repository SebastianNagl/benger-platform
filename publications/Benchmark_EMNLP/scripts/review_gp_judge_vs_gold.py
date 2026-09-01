"""List Grundprinzipien generations where the GPT-5.4-mini judge's correctness
assessment deviates from the objective gold Ja/Nein label, for manual review.

GP is the only corpus with a ground-truth decision label
(task.data.binary_solution), so it is the one place the judge can be checked
against truth rather than against (noisy) human grades.

Caveat baked into the output: the judge's `result_correctness` dimension blends
decision correctness WITH reasoning quality (see the judge_reason column), so:
  - direction=harsh  (gold-right, judge-correctness low) is usually legitimate
    -- a correct decision with weak reasoning.
  - direction=lenient (gold-wrong, judge-correctness high) is the real concern
    -- the judge crediting an objectively wrong decision. Sorted first, by
    descending correctness (most egregious at the top).

    uv run python scripts/review_gp_judge_vs_gold.py

Output: data/processed/error_review_gp_judge_vs_gold.csv
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path


def _decision(x):
    """Normalise a Ja/Nein decision: strip case, whitespace, trailing punctuation."""
    if x is None:
        return None
    m = re.match(r"\s*(ja|nein)", str(x).strip().lower())
    return m.group(1) if m else str(x).strip().lower().rstrip(". ")

HERE = Path(__file__).resolve().parent.parent
SRC = HERE / "data" / "raw" / "grundprinzipien" / "grundprinzipien_Grundprinzipien_full_export.json"
OUT = HERE / "data" / "processed" / "error_review_gp_judge_vs_gold.csv"
GP_PREFIX = "llm_judge_custom-mpu1cuad"
RC_MAX, SUB_MAX = 40.0, 25.0
RC_THRESHOLD = 0.50          # "judge says correct" := result_correctness >= 0.50*max


def _clip(s, n):
    return " ".join(str(s or "")[:n].split())


def main():
    export = json.load(open(SRC, encoding="utf-8"))
    rows = []
    for t in export.get("tasks", []):
        data = t.get("data") or {}
        gold = data.get("binary_solution")
        question = data.get("fall")
        bereich = data.get("Bereich")
        for g in (t.get("generations") or []):
            mid = g.get("model_id")
            if not mid:
                continue
            rc_score = rc_reason = sub_score = judge_total = acc = None
            for ev in (g.get("evaluations") or []):
                fn = str(ev.get("field_name") or "")
                m = ev.get("metrics") or {}
                if fn.startswith(GP_PREFIX) and isinstance(m.get("llm_judge_custom"), dict):
                    det = m["llm_judge_custom"].get("details") or {}
                    sc = det.get("scores") or {}
                    rcd = sc.get("result_correctness") or {}
                    rc_score = rcd.get("score")
                    rc_reason = rcd.get("reason")
                    sub_score = (sc.get("subsumption") or {}).get("score")
                    judge_total = det.get("total_score")
                if acc is None and isinstance(m.get("accuracy"), dict):
                    v = m["accuracy"].get("value")
                    if v is not None:
                        acc = int(round(float(v)))
            if rc_score is None or acc is None:
                continue
            rc_frac = float(rc_score) / RC_MAX
            judge_correct = rc_frac >= RC_THRESHOLD
            if (acc == 1) == judge_correct:
                continue  # judge agrees with gold -> not a deviation
            direction = "lenient" if (acc == 0 and judge_correct) else "harsh"

            # model's stated Ja/Nein + reasoning
            model_dec = model_reason = None
            rc = g.get("response_content")
            if isinstance(rc, str):
                try:
                    parsed = json.loads(rc)
                    model_dec = parsed.get("kurzantwort")
                    model_reason = parsed.get("begruendung")
                except Exception:
                    model_reason = rc
            norm_match = (_decision(model_dec) is not None
                          and _decision(model_dec) == _decision(gold))
            rows.append({
                "direction": direction,
                "metric_bug": int(acc == 0 and norm_match),  # false mismatch: decisions agree once normalised
                "system": mid,
                "bereich": bereich,
                "task_id": t.get("id"),
                "generation_id": g.get("id"),
                "gold_decision": _clip(gold, 60),
                "model_decision": _clip(model_dec, 60),
                "accuracy_match": acc,
                "norm_match": int(norm_match),
                "result_correctness_40": rc_score,
                "result_correctness_frac": round(rc_frac, 3),
                "subsumption_25": sub_score,
                "judge_total_100": judge_total,
                "question": _clip(question, 700),
                "model_begruendung": _clip(model_reason, 700),
                "judge_reason": _clip(rc_reason, 700),
            })

    # lenient first (worst judge over-credit at top), then harsh
    rows.sort(key=lambda r: (r["direction"] != "lenient",
                             -r["result_correctness_frac"] if r["direction"] == "lenient"
                             else r["result_correctness_frac"]))

    cols = ["direction", "metric_bug", "system", "bereich", "task_id", "generation_id",
            "gold_decision", "model_decision", "accuracy_match", "norm_match",
            "result_correctness_40", "result_correctness_frac", "subsumption_25",
            "judge_total_100", "question", "model_begruendung", "judge_reason"]
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    n_len = sum(1 for r in rows if r["direction"] == "lenient")
    n_harsh = len(rows) - n_len
    n_bug = sum(r["metric_bug"] for r in rows)
    genuine_len = sum(1 for r in rows if r["direction"] == "lenient" and not r["metric_bug"])
    print(f"wrote {OUT.name}: {len(rows)} deviation cases "
          f"({n_len} lenient, {n_harsh} harsh)")
    print(f"  metric_bug=1 (decisions agree once normalised; accuracy false-mismatch): {n_bug}")
    print(f"  GENUINE lenient deviations (judge credits a truly wrong decision): {genuine_len}")


if __name__ == "__main__":
    main()
