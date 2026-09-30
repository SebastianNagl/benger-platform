#!/usr/bin/env python3
"""LEXam-DE headline tables from the prod dumps (run dump_results.sh first).

Computes, per model x project:
  - mean judge score x100 per judge model (gpt-5-mini, gpt-5.4-mini)
  - the judge mean and the pointwise MIN across the two judges (the house
    analogue of LEXam v4+'s min-ensemble; the min is taken per (task,
    generation) before averaging, exactly like the paper's pooling)
  - bootstrap standard errors (1000 resamples, seeded like LEXam)
  - Grundprinzipien binary accuracy vs the 50% random baseline
  - diagnostics: truncation rate, judge-error rate, <think> contamination
  - per-Bereich splits (LEXam's area analysis)
  - the German-vs-Swiss anchor comparison for models with published LEXam
    open-question scores (min-ensemble numbers, arXiv:2505.12864 v7 Table 1)

Usage: python3 lexam_report.py [datadir] > report.md
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent / "data")
RNG_SEED = 42
N_BOOT = 1000

# LEXam v7 Table 1 (open questions, min-ensemble judge, 0-100).
LEXAM_SWISS_OQ = {
    "gpt-4o-mini": 42.55,
    "gpt-4.1-mini": 54.58,
    "google/gemma-3-12b-it": 41.29,
}


def read_dump(path: Path) -> pd.DataFrame:
    """Read a dump_results.sh TSV: psql -A output whose separator arrives as
    the LITERAL two characters backslash-t (SSH quoting), with a trailing
    '(N rows)' footer line."""
    import io
    lines = path.read_text().splitlines()
    if lines and lines[-1].strip().endswith("rows)"):
        lines = lines[:-1]
    normalized = "\n".join(line.replace("\\t", "\t") for line in lines)
    return pd.read_csv(io.StringIO(normalized), sep="\t", dtype=str)


def boot_se(values: np.ndarray) -> float:
    if len(values) == 0:
        return float("nan")
    rng = np.random.default_rng(RNG_SEED)
    means = [rng.choice(values, size=len(values), replace=True).mean() for _ in range(N_BOOT)]
    return float(np.std(means))


def main() -> None:
    cells = read_dump(DATA / "judge_cells.tsv")
    cells = cells[cells["score"].notna()].copy()
    cells["score"] = cells["score"].astype(float)

    gens = read_dump(DATA / "generations.tsv")

    print("# LEXam-DE results\n")

    # --- open-question track: per (project, model) judge table -------------
    model_cells = cells[cells["generation_id"].notna() & (cells["structure_key"] == "lexam-open")]
    rows = []
    for (project, model), grp in model_cells.groupby(["project", "model_id"]):
        per_judge = {}
        for judge, jgrp in grp.groupby("judge_model_id"):
            per_judge[judge] = jgrp.set_index(["task_id", "generation_id"])["score"]
        wide = pd.DataFrame(per_judge)
        pointwise_min = wide.min(axis=1).to_numpy() * 100
        row = {
            "project": project,
            "model": model,
            "n": len(wide),
            "min_ensemble": pointwise_min.mean(),
            "min_se": boot_se(pointwise_min),
        }
        for judge in sorted(per_judge):
            vals = wide[judge].dropna().to_numpy() * 100
            row[judge] = vals.mean()
            row[f"{judge}_se"] = boot_se(vals)
        rows.append(row)
    open_table = pd.DataFrame(rows).sort_values(["project", "min_ensemble"], ascending=[True, False])
    print("## Open-question track (judge score x100; min = 2-judge pointwise minimum)\n")
    print(open_table.to_markdown(index=False, floatfmt=".2f"))

    # --- human baseline (Benchathon annotation cells) ----------------------
    human = cells[cells["annotation_id"].notna()]
    if len(human):
        h = human.groupby("judge_model_id")["score"].agg(["count", "mean"])
        h["mean"] *= 100
        print("\n## Benchathon human submissions under the identical judge\n")
        print(h.to_markdown(floatfmt=".2f"))

    # --- binary track ------------------------------------------------------
    bpath = DATA / "binary_cells.tsv"
    if bpath.exists() and bpath.stat().st_size > 0:
        b = read_dump(bpath)
        if len(b):
            b["exact_match"] = b["exact_match"].astype(float)
            acc = b.groupby("model_id")["exact_match"].agg(["count", "mean"])
            acc["mean"] *= 100
            acc = acc.sort_values("mean", ascending=False)
            print("\n## Grundprinzipien binary track (accuracy %, random baseline 50)\n")
            print(acc.to_markdown(floatfmt=".2f"))

    # --- Swiss anchors ------------------------------------------------------
    anchors = open_table[open_table["model"].isin(LEXAM_SWISS_OQ)]
    if len(anchors):
        a = anchors[["project", "model", "min_ensemble"]].copy()
        a["lexam_swiss_oq"] = a["model"].map(LEXAM_SWISS_OQ)
        a["delta"] = a["min_ensemble"] - a["lexam_swiss_oq"]
        print("\n## German-vs-Swiss anchors (min-ensemble vs LEXam v7 Table 1)\n")
        print(a.to_markdown(index=False, floatfmt=".2f"))

    # --- per-Bereich splits -------------------------------------------------
    by_area = (
        model_cells.groupby(["project", "bereich"])["score"].agg(["count", "mean"])
    )
    by_area["mean"] *= 100
    print("\n## Per-Bereich means (all models x judges pooled)\n")
    print(by_area.to_markdown(floatfmt=".2f"))

    # --- diagnostics --------------------------------------------------------
    print("\n## Diagnostics\n")
    lex = gens[gens["structure_key"].isin(["lexam-open", "lexam-binary"])].copy()
    # psql -A renders booleans as t/f strings; tokens arrive as strings too.
    lex["output_tokens"] = pd.to_numeric(lex["output_tokens"], errors="coerce")
    diag = lex.groupby(["project", "structure_key", "model_id"]).agg(
        n=("task_id", "count"),
        truncated=("truncated", lambda s: (s == "t").mean()),
        think=("has_think_tag", lambda s: (s == "t").mean()),
        mean_out_tokens=("output_tokens", "mean"),
    )
    print(diag.to_markdown(floatfmt=".3f"))
    err_rate = cells["metric_error"].notna().mean() if "metric_error" in cells else 0.0
    zero_scores = (cells["score"] == 0.0).mean()
    print(f"\n- judge-cell error rate: {err_rate:.4f}")
    print(f"- share of 0.0 scores (includes genuine zeros AND parse-failure zeros): {zero_scores:.4f}")


if __name__ == "__main__":
    main()
