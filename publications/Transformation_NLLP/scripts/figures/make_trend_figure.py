#!/usr/bin/env python3
"""Reliability figures (RQ2).

fig_trend.pdf  (body, Figure 2): Luna instrument-progression trend
(holistic → zero-shot → few-shot) at full column width, with the in-sample
selection floor as a dashed reference.
fig_forest.pdf (appendix): per-judge forest of the matched within-judge
repeat-SD effect (tailored − holistic, exam-cluster bootstrap 95% CIs) for
the five capable judges + Mini (shown, not pooled) + the pooled estimate.

Print-safe grayscale, one measure per axis; identity by row position and
marker shape (filled = pooled judges, open = below-floor Mini, diamond =
pooled), never by hue.

Reads  data/processed/trend_figure_data.json  (trend;  script-written)
       data/processed/matched_multijudge.json (forest; script-written)
Writes assets/fig_trend.pdf, assets/fig_forest.pdf

Usage: uv run python scripts/figures/make_trend_figure.py
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("pdf")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent.parent.parent
TREND = HERE / "data" / "processed" / "trend_figure_data.json"
FOREST = HERE / "data" / "processed" / "matched_multijudge.json"
OUT_TREND = HERE / "assets" / "fig_trend.pdf"
OUT_FOREST = HERE / "assets" / "fig_forest.pdf"

plt.rcParams.update({
    "font.family": "serif", "font.size": 8, "axes.linewidth": 0.6,
    "pdf.fonttype": 42, "ps.fonttype": 42,
})

INK = "#1a1a1a"
GRAY = "#6b6b6b"
GRID = "#e2e2e2"


def make_trend(trend) -> None:
    labels = ["Holistic", "Zero-shot", "Few-shot"]
    keys = ["holistic", "zeroshot", "fewshot"]
    xs = [0, 1, 2]
    means = [trend[k][0] for k in keys]
    los = [trend[k][0] - trend[k][1] for k in keys]
    his = [trend[k][2] - trend[k][0] for k in keys]

    fig, ax = plt.subplots(figsize=(3.15, 1.55))

    ax.axhline(trend["oracle"], ls=(0, (4, 3)), lw=0.8, color=GRAY, zorder=1)
    ax.text(-0.3, trend["oracle"] + 0.06,
            f"in-sample floor {trend['oracle']:.2f} (post hoc)",
            va="bottom", ha="left", fontsize=6.5, color=GRAY)

    ax.plot(xs, means, "-", lw=1.4, color=INK, zorder=3)
    ax.errorbar(xs, means, yerr=[los, his], fmt="o", ms=5, color=INK,
                ecolor=INK, elinewidth=1.0, capsize=2.5, capthick=1.0, zorder=4)
    for x, m in zip(xs, means):
        ax.annotate(f"{m:.2f}", (x, m), textcoords="offset points",
                    xytext=(7, 4), fontsize=7, color=INK)

    ax.set_xticks(xs)
    ax.set_xticklabels(labels, fontsize=7.5)
    ax.set_xlim(-0.35, 2.55)
    ax.set_ylim(0.8, 2.9)
    ax.set_ylabel("repeat SD (Luna ×3)", fontsize=7)
    ax.tick_params(length=2.5, labelsize=7.5)
    ax.grid(axis="y", lw=0.4, color=GRID, zorder=0)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)

    fig.tight_layout(pad=0.3)
    fig.savefig(OUT_TREND)
    print(f"wrote {OUT_TREND.relative_to(HERE)}")


def make_forest(mj) -> None:
    forest = mj["forest"]
    pooled = mj["pooled"]

    fig, ax = plt.subplots(figsize=(3.15, 2.0))

    XLIM = (-1.55, 2.55)
    rows = forest + [{"label": "Pooled", "delta": pooled["point"],
                      "ci95": pooled["ci95"], "pooled_row": True}]
    n = len(rows)
    ys = list(range(n - 1, -1, -1))          # top -> bottom
    ys[-1] -= 0.45                            # gap before the pooled row

    ax.axvline(0.0, lw=0.7, color=GRAY, zorder=1)
    for r, y in zip(rows, ys):
        lo, hi = r["ci95"]
        clo, chi = max(lo, XLIM[0] + 0.03), min(hi, XLIM[1] - 0.03)
        ax.plot([clo, chi], [y, y], lw=1.0, color=INK, zorder=3,
                solid_capstyle="butt")
        if lo < XLIM[0] + 0.03:               # clipped whisker: print the bound
            ax.annotate(f"{lo:+.1f}", (XLIM[0] + 0.05, y), fontsize=5.5,
                        color=GRAY, va="bottom", ha="left",
                        textcoords="offset points", xytext=(0, 1.5))
        if hi > XLIM[1] - 0.03:
            ax.annotate(f"{hi:+.1f}", (XLIM[1] - 0.05, y), fontsize=5.5,
                        color=GRAY, va="bottom", ha="right",
                        textcoords="offset points", xytext=(0, 1.5))
        if r.get("pooled_row"):
            ax.plot([r["delta"]], [y], marker="D", ms=4.8, mfc=INK, mec=INK,
                    zorder=4)
            ax.annotate(f"{r['delta']:+.2f}", (r["delta"], y),
                        textcoords="offset points", xytext=(0, -9.5),
                        fontsize=6.2, color=INK, ha="center")
        elif not r.get("in_pooled", True):    # Mini: open marker, not pooled
            ax.plot([r["delta"]], [y], marker="o", ms=4.8, mfc="white",
                    mec=INK, mew=1.1, zorder=4)
        else:
            ax.plot([r["delta"]], [y], marker="o", ms=4.8, mfc=INK, mec=INK,
                    zorder=4)

    ax.set_yticks(ys)
    ax.set_yticklabels([r["label"] for r in rows], fontsize=7)
    ax.set_xlim(*XLIM)
    ax.set_ylim(min(ys) - 0.75, max(ys) + 0.6)
    ax.set_xticks([-1, 0, 1, 2])
    ax.set_xlabel("Δ repeat SD (tailored − holistic)", fontsize=7, labelpad=2)
    ax.tick_params(length=2.5, labelsize=7)
    ax.grid(axis="x", lw=0.4, color=GRID, zorder=0)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.tick_params(axis="y", length=0)

    fig.tight_layout(pad=0.3)
    fig.savefig(OUT_FOREST)
    print(f"wrote {OUT_FOREST.relative_to(HERE)}")


def main() -> int:
    make_trend(json.loads(TREND.read_text()))
    make_forest(json.loads(FOREST.read_text()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
