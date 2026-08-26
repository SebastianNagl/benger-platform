#!/usr/bin/env python3
"""The abstract's central analytic move: how far do NLP similarity metrics
predict doctrinal rubric scores on German exam answers?

Input: data/paired_metrics.tsv (one row per (cell, metric-config), columns:
project_id, task_id, generation_id, model_id, bereich_raw, field_name,
metrics_kv as 'k=v;k=v'). Pivots to one row per generation with all metrics,
then reports:
  - Pearson + Spearman correlation of each similarity metric vs the
    Falllösung rubric score (gpt-5.4-mini judge config), per project
  - mismatch quadrants (top/bottom terciles of similarity vs rubric)
  - example mismatch cells for qualitative inspection (ids only)
"""

from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ZJS = "0fefa5c8-29c7-4eb5-b107-c2271f2288f9"
BENCH = "e529779b-300f-48c0-89cb-90f3f4b72a51"
SIM_METRICS = ["bleu", "rouge", "meteor", "semantic_similarity", "bertscore", "moverscore"]
# gpt-5.4-mini falloesung judge configs (vs the gpt-5-nano / gpt-5-mini ones)
RUBRIC_CFG_PREFIX = {"llm_judge_falloesung-mptrd45m", "llm_judge_falloesung-mpe7o02k",
                     "llm_judge_falloesung-mpup3ejd"}


def main() -> None:
    rows = []
    for line in (HERE / "data" / "paired_metrics.tsv").read_text().splitlines():
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        project, task, gen, model, bereich, field_name, kv = parts[:7]
        cfg = field_name.split("|")[0]
        for pair in kv.split(";"):
            if "=" not in pair:
                continue
            k, v = pair.split("=", 1)
            try:
                v = float(v)
            except ValueError:
                continue
            if k == "llm_judge_falloesung":
                cfg_root = "-".join(cfg.split("-")[:2])
                if cfg_root not in RUBRIC_CFG_PREFIX:
                    continue  # keep only the gpt-5.4-mini judge configs
                k = "rubric"
            rows.append({"project": project, "task": task, "gen": gen,
                         "model": model, "bereich": bereich, "metric": k, "value": v})
    df = pd.DataFrame(rows)
    wide = df.pivot_table(index=["project", "task", "gen", "model", "bereich"],
                          columns="metric", values="value", aggfunc="mean").reset_index()

    for project, label in ((ZJS, "ZJS Fälle"), (BENCH, "Benchathon")):
        sub = wide[wide["project"] == project].dropna(subset=["rubric"])
        print(f"\n## {label}: similarity vs 100-point rubric (n={len(sub)} generations)\n")
        print("| metric | Pearson r | Spearman rho | n |")
        print("|---|---|---|---|")
        for m in SIM_METRICS:
            if m not in sub.columns:
                continue
            pair = sub.dropna(subset=[m])
            if len(pair) < 30:
                continue
            r = np.corrcoef(pair[m], pair["rubric"])[0, 1]
            rho = pair[[m, "rubric"]].rank().corr().iloc[0, 1]
            print(f"| {m} | {r:.3f} | {rho:.3f} | {len(pair)} |")

        # Mismatch quadrants on the best available semantic metric
        best = "bertscore" if "bertscore" in sub.columns else "semantic_similarity"
        pair = sub.dropna(subset=[best])
        if len(pair) >= 90:
            s_hi = pair[best] >= pair[best].quantile(2 / 3)
            s_lo = pair[best] <= pair[best].quantile(1 / 3)
            r_hi = pair["rubric"] >= pair["rubric"].quantile(2 / 3)
            r_lo = pair["rubric"] <= pair["rubric"].quantile(1 / 3)
            n = len(pair)
            print(f"\nQuadrants on {best} terciles (share of all {n} cells):")
            print(f"- aligned high/high: {(s_hi & r_hi).mean()*100:.1f}%")
            print(f"- aligned low/low:   {(s_lo & r_lo).mean()*100:.1f}%")
            print(f"- MISMATCH high-sim / low-rubric: {(s_hi & r_lo).mean()*100:.1f}%")
            print(f"- MISMATCH low-sim / high-rubric: {(s_lo & r_hi).mean()*100:.1f}%")
            mism = pair[s_hi & r_lo].nlargest(3, best)
            for _, row in mism.iterrows():
                print(f"  example high-sim/low-rubric: gen={row['gen'][:8]} model={row['model']} "
                      f"{best}={row[best]:.3f} rubric={row['rubric']*100:.0f}")

    # Cross-project: does the correlation weaken with difficulty?
    print("\n## Difficulty contrast (Spearman rho, semantic_similarity vs rubric)\n")
    for project, label in ((BENCH, "Benchathon (medium)"), (ZJS, "ZJS (hard)")):
        sub = wide[(wide["project"] == project)].dropna(subset=["rubric", "semantic_similarity"])
        if len(sub) < 30:
            continue
        rho = sub[["semantic_similarity", "rubric"]].rank().corr().iloc[0, 1]
        print(f"- {label}: rho={rho:.3f} (n={len(sub)})")

    wide.to_csv(HERE / "data" / "paired_wide.csv", index=False)
    print("\nwrote data/paired_wide.csv")


if __name__ == "__main__":
    main()
