#!/usr/bin/env python3
"""Minimum detectable effects for the two planned contrasts (exploratory).

Both contrasts are paired over items. Their spread is estimated from the
closest existing contrast, Luna tailored vs Luna holistic on the 45 matched
cells (data/processed/matched_stats.json, per_pick), so the MDEs are proxies
until the new instrument's own pilot data exist.

  C1  repeat SD, new instrument vs first-iteration instrument, 45 D1 picks.
      Proxy d_i = tailored repeat SD - holistic repeat SD (3 passes each).
      Also a projection for 5 passes: the variance of a sample SD scales with
      1/(k-1), so if the paired spread were pure sampling noise it would
      shrink by sqrt(2/4). That is an optimistic bound.
  C2  absolute error vs the expert, new instrument vs the expert's sheet, D2
      scripts. Proxy e_i = |tailored - human| - |holistic - human| on the 30
      D1 annotation picks with a blind-human pool mean (a holistic, noisier
      reference than per-step expert grades). Reported for the D2
      counts: n = 15 (D2a, graded) and n = 38 (once D2b is graded: every distinct D2 script: 15 D2a + 23
      D2b students after excluding the author's test upload and the
      duplicate of H11). Two D2b scripts share 26 % of their 8-grams, so
      they are one dependent pair; n = 37 counts them once.

MDE = (t_{1-alpha/2, n-1} + t_{power, n-1}) * sd / sqrt(n), the paired
t-test approximation; Holm over two contrasts puts the first test at
alpha = .025. A Wilcoxon signed-rank test needs about 1/0.955 as many pairs
(ARE).

Input: data/processed/matched_stats.json (tracked).
Output: data/processed/mde.json
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

from scipy.stats import t as student_t

HERE = Path(__file__).resolve().parent.parent.parent
IN = HERE / "data" / "processed" / "matched_stats.json"
OUT = HERE / "data" / "processed" / "mde.json"
POWER = 0.8
ALPHAS = (0.025, 0.05)
# D2 script counts (data/interim/human/heidebach_pack_report.json): 15 D2a,
# 38 distinct D2 scripts, 37 when the dependent pair counts once.
D2_N = {"n_15_d2a": 15, "n_38_all_distinct": 38, "n_37_dependent_pair_once": 37}


def mde(sd: float, n: int, alpha: float, power: float = POWER) -> float:
    df = n - 1
    return (student_t.ppf(1 - alpha / 2, df) + student_t.ppf(power, df)) * sd / n ** 0.5


def main() -> int:
    per_pick = json.loads(IN.read_text())["per_pick"]

    d = [p["luna_tail_rep_sd"] - p["luna_holi_rep_sd"] for p in per_pick
         if p.get("luna_tail_rep_sd") is not None and p.get("luna_holi_rep_sd") is not None]
    sd_d = statistics.stdev(d)
    c1 = {
        "proxy": "Luna tailored minus Luna holistic repeat SD, 3 passes, 45 picks",
        "n": len(d),
        "observed_mean_difference": round(statistics.mean(d), 3),
        "sd_of_differences": round(sd_d, 3),
        "mde": {f"alpha_{a}": round(mde(sd_d, len(d), a), 3) for a in ALPHAS},
        "mde_5_passes_optimistic": {f"alpha_{a}": round(mde(sd_d * (2 / 4) ** 0.5, len(d), a), 3)
                                    for a in ALPHAS},
    }

    ann = [p for p in per_pick if p["target_type"] == "annotation" and p.get("human_mean") is not None
           and p.get("luna_tail_first") is not None and p.get("luna_holi_first") is not None]
    e = [abs(p["luna_tail_first"] - p["human_mean"]) - abs(p["luna_holi_first"] - p["human_mean"])
         for p in ann]
    sd_e = statistics.stdev(e)
    c2 = {
        "proxy": "|Luna tailored - human| minus |Luna holistic - human|, first pass, D1 annotation picks",
        "n_proxy": len(e),
        "observed_mean_difference": round(statistics.mean(e), 3),
        "sd_of_differences": round(sd_e, 3),
        "mde": {name: {f"alpha_{a}": round(mde(sd_e, n, a), 2) for a in ALPHAS} for name, n in D2_N.items()},
    }

    out = {"note": "Paired t-based MDEs at power 0.8 from proxy spreads (exploratory); recompute from the new "
                   "instrument's pilot data.",
           "C1_repeat_sd": c1, "C2_abs_error_vs_expert": c2}
    OUT.write_text(json.dumps(out, indent=1) + "\n")

    print(f"C1 repeat SD (n={c1['n']}): sd_d {c1['sd_of_differences']:.2f}, observed "
          f"{c1['observed_mean_difference']:+.2f}; MDE {c1['mde']['alpha_0.025']:.2f} (alpha .025), "
          f"{c1['mde']['alpha_0.05']:.2f} (.05); 5 passes <= {c1['mde_5_passes_optimistic']['alpha_0.025']:.2f}")
    print(f"C2 abs error (proxy n={c2['n_proxy']}): sd_e {c2['sd_of_differences']:.2f}, observed "
          f"{c2['observed_mean_difference']:+.2f}; MDE (alpha .025) "
          + ", ".join(f"{name} {v['alpha_0.025']:.1f}" for name, v in c2["mde"].items()) + " points")
    print(f"-> {OUT.relative_to(HERE)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
